"""Safe Exam Browser (SEB): an optional lock-down for laptop and iPad sittings.

SEB proves which configuration it runs with through the Config Key (CK): for a page at URL u it sends
    SHA256(u without #fragment + CK)            (hex)
in the header X-SafeExamBrowser-ConfigKeyHash, and exposes the same value to the page as
SafeExamBrowser.security.configKey (JavaScript API). Our React app reads that value once with the page URL it was
computed for and sends both with every API call (X-SEB-Config-Key-Hash, X-SEB-Page-Url), because API calls go to
other URLs than the page. https://safeexambrowser.org/developer/seb-config-key.html

What this proves: the exam runs in SEB with the configuration the admin uploaded. It is a strong barrier against
casual bypass, not against someone who extracts the key from the .seb file and forges the header; the behaviour
signals keep working either way. SEB has no Android version, so it is never switched on by default, and when a
sitting requires it, it is required on laptops and desktops only: phones and tablets use kiosk mode
(services/device.py), and a browser that only pretends to be a phone gets a "device check" flag.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
import secrets
from urllib.parse import urlsplit, urlunsplit

from .. import db
from ..http import ApiError

KEY = re.compile(r"^[0-9a-f]{64}$")
DOWNLOAD = "https://safeexambrowser.org/download_en.html"


def _hash(url: str, key: str) -> str:
    u = urlsplit(url)
    return hashlib.sha256((urlunsplit((u.scheme, u.netloc, u.path, u.query, "")) + key).encode("utf-8")).hexdigest()


def _hosts(request) -> set[str]:
    h = {request.headers.get("host", ""), request.headers.get("x-forwarded-host", "")}
    return {x.split(",")[0].strip().lower() for x in h if x}


def verified(request, key: str | None) -> bool:
    if not key:
        return False
    key = key.lower()
    hosts = _hosts(request)
    # 1. the page's JavaScript API value, for the page URL it was computed with (same site only)
    # (the page sends the URL it loaded with and the current one: SEB versions differ in which they hash after
    # the single-page app changes its address)
    sent = request.headers.get("x-seb-config-key-hash", "").lower()
    for page in {request.headers.get("x-seb-page-url", ""), request.headers.get("x-seb-page-url-now", "")}:
        if page and sent and urlsplit(page).netloc.lower() in hosts and secrets.compare_digest(_hash(page, key), sent):
            return True
    # 2. SEB's own header, for this request's URL (behind a tunnel the scheme or host may differ: try both)
    native = request.headers.get("x-safeexambrowser-configkeyhash", "")
    if native:
        u = request.url
        schemes = {request.headers.get("x-forwarded-proto", "").split(",")[0].strip() or u.scheme, "https", "http"}
        for scheme in schemes:
            for host in hosts:
                url = urlunsplit((scheme, host, u.path, u.query, ""))
                if secrets.compare_digest(_hash(url, key), native.lower()):
                    return True
    return False


def in_seb(request) -> bool:
    ua = request.headers.get("user-agent", "")
    return "SEB" in ua or bool(request.headers.get("x-seb-config-key-hash")) or \
        bool(request.headers.get("x-safeexambrowser-configkeyhash"))


def info(sit: dict, request) -> dict:
    """What the candidate page needs: whether SEB is required, where the .seb file is, and if this request passed.
    SEB is required on laptops and desktops only: there is no SEB for Android, so phones and tablets use kiosk mode."""
    from .device import is_mobile
    if not sit.get("seb_required"):
        return dict(required=False)
    if is_mobile(request) and not in_seb(request):
        return dict(required=False, exempt="phone")
    return dict(required=True, verified=verified(request, sit.get("seb_config_key")), in_seb=in_seb(request),
                config_url=f"/api/seb/{sit['seb_token']}.seb" if sit.get("seb_file") and sit.get("seb_token") else None,
                download_url=DOWNLOAD)


def guard(con, request, session: dict) -> None:
    """Raise unless the sitting does not require SEB or this request comes from SEB with the right configuration."""
    from .device import is_mobile
    sit = db.one(con, "SELECT * FROM sittings WHERE id = ?", session["sitting_id"])
    if sit and sit.get("seb_required") and not verified(request, sit.get("seb_config_key")) \
            and not (is_mobile(request) and not in_seb(request)):     # phones: kiosk mode (checked by the device check)
        raise ApiError(403, "seb_required", "This test opens only in Safe Exam Browser with the test's settings.",
                       seb=info(sit, request))


def configure(con, sitting_id: int, required: bool, config_key: str | None, file_b64: str | None, clear_file: bool) -> dict:
    sit = db.one(con, "SELECT * FROM sittings WHERE id = ?", sitting_id)
    if not sit:
        raise ApiError(404, "not_found", "Sitting not found.")
    key = (config_key or "").strip().lower() or sit.get("seb_config_key")
    if config_key is not None and config_key.strip() and not KEY.match(key):
        raise ApiError(422, "bad_config_key", "The Config Key is 64 hexadecimal characters (copy it from the SEB Config Tool).")
    if required and not key:
        raise ApiError(422, "config_key_needed", "Add the Config Key before requiring Safe Exam Browser.")
    file = sit.get("seb_file")
    if clear_file:
        file = None
    if file_b64:
        try:
            raw = base64.b64decode(file_b64.split(",", 1)[-1], validate=True)
        except (binascii.Error, ValueError):
            raise ApiError(422, "bad_seb_file", "The .seb file could not be read.")
        if not raw or len(raw) > 2_000_000:
            raise ApiError(422, "bad_seb_file", "The .seb file is empty or larger than 2 MB.")
        file = base64.b64encode(raw).decode()
    token = sit.get("seb_token") or secrets.token_urlsafe(12)
    con.execute("UPDATE sittings SET seb_required = ?, seb_config_key = ?, seb_file = ?, seb_token = ? WHERE id = ?",
                (int(required), key or None, file, token, sitting_id))
    return summary(db.one(con, "SELECT * FROM sittings WHERE id = ?", sitting_id))


def summary(sit: dict) -> dict:
    return dict(required=bool(sit.get("seb_required")), config_key_set=bool(sit.get("seb_config_key")),
                config_key_end=(sit.get("seb_config_key") or "")[-6:], file_uploaded=bool(sit.get("seb_file")),
                config_url=f"/api/seb/{sit['seb_token']}.seb" if sit.get("seb_file") and sit.get("seb_token") else None)
