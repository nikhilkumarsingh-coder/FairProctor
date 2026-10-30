"""A minimal in-process HTTP client for the ASGI app (no httpx needed).

Remembers the JWT from login/signup and sends it as `Authorization: Bearer ...`;
with cookies=True it also keeps cookies like a browser on the same origin.
"""
from __future__ import annotations

import asyncio
import json
from http.cookies import SimpleCookie
from urllib.parse import urlsplit


class Resp:
    def __init__(self, status, headers, body):
        self.status_code, self.headers, self.content = status, headers, body

    @property
    def text(self):
        return self.content.decode()

    def json(self):
        return json.loads(self.content or b"null")


class Client:
    def __init__(self, app, cookies: bool = False):
        self.app, self.cookies, self.use_cookies, self.token = app, {}, cookies, None

    def request(self, method, url, json_body=None, data=None, headers=None):
        parts = urlsplit(url)
        body = json.dumps(json_body).encode() if json_body is not None else (data.encode() if isinstance(data, str) else data or b"")
        hdrs = {"host": "testserver"}
        if json_body is not None:
            hdrs["content-type"] = "application/json"
        hdrs.update({k.lower(): v for k, v in (headers or {}).items()})
        if self.token and "authorization" not in hdrs:
            hdrs["authorization"] = f"Bearer {self.token}"
        if self.use_cookies and self.cookies:
            hdrs["cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        scope = dict(type="http", asgi={"version": "3.0"}, http_version="1.1", method=method, scheme="http",
                     path=parts.path, raw_path=parts.path.encode(), query_string=parts.query.encode(), root_path="",
                     headers=[(k.encode(), v.encode()) for k, v in hdrs.items()], client=("127.0.0.1", 1),
                     server=("testserver", 80))
        out = dict(status=None, headers=[], body=b"")
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return dict(type="http.request", body=body, more_body=False)
            return dict(type="http.disconnect")

        async def send(msg):
            if msg["type"] == "http.response.start":
                out["status"], out["headers"] = msg["status"], msg["headers"]
            elif msg["type"] == "http.response.body":
                out["body"] += msg.get("body", b"")

        asyncio.run(self.app(scope, receive, send))
        headers = {}
        for k, v in out["headers"]:
            k, v = k.decode().lower(), v.decode()
            if k == "set-cookie":
                c = SimpleCookie()
                c.load(v)
                for name, m in c.items():
                    if m["max-age"] == "0" or m.value in ("", '""'):
                        self.cookies.pop(name, None)
                    else:
                        self.cookies[name] = m.value
            headers[k] = v
        resp = Resp(out["status"], headers, out["body"])
        if parts.path in ("/api/auth/login", "/api/auth/signup", "/api/demo/candidate") and resp.status_code in (200, 201):
            self.token = resp.json()["access_token"]
        return resp

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, json=None, **kw):
        return self.request("POST", url, json_body=json, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)
