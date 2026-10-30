"""Request bodies. Anything not listed here is rejected before it reaches the database."""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(Strict):
    email: Optional[str] = None
    password: Optional[str] = None
    roll_no: Optional[str] = None
    code: Optional[str] = None
    app: Optional[Literal["candidate", "staff"]] = None     # which frontend: candidates and staff log in separately

    @model_validator(mode="after")
    def one_kind(self):
        staff = bool(self.email and self.password)
        cand = bool(self.roll_no and self.code)
        if staff == cand:
            raise ValueError("send either email + password, or roll_no + code")
        return self


def check_password(v: str) -> str:
    if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
        raise ValueError("use at least 8 characters with letters and numbers")
    return v


class SignupIn(Strict):
    """Self sign-up creates a candidate ('user' role). Staff accounts are made by an admin."""
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=200)
    password: str = Field(min_length=8, max_length=200)
    language: Literal["en", "hi"] = "en"

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        if not EMAIL.match(v):
            raise ValueError("enter a valid email address")
        return v.lower()

    @field_validator("password")
    @classmethod
    def _password(cls, v):
        return check_password(v)


class ProfileIn(Strict):
    """What a user may change about themselves. Role, email and roll no. are set by the system or an admin."""
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    language: Optional[Literal["en", "hi"]] = None


class ChangePasswordIn(Strict):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)

    @field_validator("new_password")
    @classmethod
    def _password(cls, v):
        return check_password(v)


class JoinIn(Strict):
    join_code: str = Field(min_length=4, max_length=20)


class UserIn(Strict):
    role: Literal["admin", "reviewer"]
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        if not EMAIL.match(v):
            raise ValueError("enter a valid email address")
        return v.lower()


class TestIn(Strict):
    title: str = Field(min_length=1, max_length=200)
    duration_min: int = Field(ge=1, le=600)
    kind: Literal["mcq", "coding"] = "mcq"


class SittingIn(Strict):
    test_id: int
    title: str = Field(min_length=1, max_length=200)
    starts_at: str      # ISO 8601, e.g. 2026-11-02T10:00:00+05:30
    ends_at: str


class SebIn(Strict):
    required: bool
    config_key: Optional[str] = Field(default=None, max_length=80)
    file_base64: Optional[str] = Field(default=None, max_length=3_000_000)     # the .seb file
    clear_file: bool = False


class DemoCandidateIn(Strict):
    kind: Literal["mcq", "coding"] = "mcq"
    language: Literal["en", "hi"] = "en"


class ReinstateIn(Strict):
    note: str = Field(min_length=5, max_length=1000)      # why the reviewer reopens it (shown in the record)


class ConsentIn(Strict):
    version: str
    understood: bool
    camera_ok: bool = True
    precheck_share_ok: bool = False


class PrecheckIn(Strict):
    brightness: Optional[float] = None
    backlight: Optional[float] = None
    face_found: Optional[bool] = None
    face_size: Optional[float] = None
    blur: Optional[float] = None
    down_kbps: Optional[float] = None
    up_kbps: Optional[float] = None
    camera_ok: Optional[bool] = None
    passed: Optional[bool] = None


class DeviceSignals(Strict):
    """What the page measured (for the device check): touch points, screen size, a coarse (finger) pointer."""
    touch: int = Field(default=0, ge=0, le=20)
    w: int = Field(default=0, ge=0, le=20000)
    h: int = Field(default=0, ge=0, le=20000)
    coarse: bool = False
    fullscreen: bool = False      # the browser can go full screen (not on iPhone)
    wake_lock: bool = False


class StartIn(Strict):
    signals: Optional[DeviceSignals] = None
    device: Literal["phone", "desktop"] = "desktop"
    bandwidth_class: Literal["low", "normal"] = "normal"
    precheck_light: Literal["ok", "dim", "bright", "backlit"] = "ok"
    precheck_framing: Literal["ok", "off_centre", "too_far", "no_face"] = "ok"


class EventIn(Strict):
    seq: int = Field(ge=1)
    t: float = Field(ge=0, le=86400)
    type: str
    item: int = -1
    option: str = Field(default="", max_length=40)   # MCQ letter, or the typed answer of a short item
    chars: int = Field(default=0, ge=0, le=1_000_000)
    meta: Optional[dict[str, float | int | str]] = None   # small numbers only, e.g. typing stats of a code editor

    @field_validator("meta")
    @classmethod
    def _small(cls, v):
        if v is not None and (len(v) > 12 or any(len(str(k)) > 20 or len(str(x)) > 40 for k, x in v.items())):
            raise ValueError("meta must be a few short numbers")
        return v


LANGUAGE = Literal["python", "cpp", "java", "javascript"]


class Exact(BaseModel):
    """Code and test data are kept exactly as typed (spaces and newlines matter)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class CodeRunIn(Exact):
    item: int = Field(ge=0)
    language: LANGUAGE
    code: str = Field(max_length=64_000)
    input: Optional[str] = Field(default=None, max_length=20_000)   # None: the sample tests; text: "run with my input"
    t: Optional[float] = Field(default=None, ge=0, le=86400)


class CodeSubmitIn(Exact):
    item: int = Field(ge=0)
    language: LANGUAGE
    code: str = Field(min_length=1, max_length=64_000)
    t: Optional[float] = Field(default=None, ge=0, le=86400)


class CaseIn(Exact):
    input: str = Field(default="", max_length=3_000_000)     # big tests check speed (e.g. 200000 numbers)
    output: str = Field(max_length=1_000_000)


class SolutionIn(Exact):
    language: LANGUAGE
    code: str = Field(min_length=1, max_length=64_000)


class ProblemIn(Exact):
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=20_000)
    languages: list[LANGUAGE] = Field(default_factory=lambda: ["python", "cpp", "java", "javascript"], min_length=1)
    time_limit: float = Field(default=2.0, gt=0, le=10)
    starter: dict[str, str] = Field(default_factory=dict)
    samples: list[CaseIn] = Field(min_length=1, max_length=10)
    tests: list[CaseIn] = Field(min_length=1, max_length=50)          # hidden
    solution: Optional[SolutionIn] = None                             # checked against every test on upload

    @field_validator("starter")
    @classmethod
    def _starter(cls, v):
        bad = set(v) - {"python", "cpp", "java", "javascript"}
        if bad:
            raise ValueError(f"unknown language in starter: {', '.join(sorted(bad))}")
        if any(len(c) > 20_000 for c in v.values()):
            raise ValueError("starter code is too long")
        return v


class ProblemSetIn(Exact):
    problems: list[ProblemIn] = Field(min_length=1, max_length=20)


class FrameIn(Strict):
    seq: int = Field(ge=1)
    t: float = Field(ge=0, le=86400)
    faces: int = Field(ge=0, le=20)
    face_visible: bool
    gaze: str = "unknown"
    brightness: Optional[float] = Field(default=None, ge=0, le=255)
    blur: Optional[float] = Field(default=None, ge=0, le=1)
    phone: Optional[float] = Field(default=None, ge=0, le=1)    # share of seconds with a phone in view; None = not checked


class EventBatchIn(Strict):
    events: list[EventIn] = Field(default_factory=list, max_length=2000)
    frames: list[FrameIn] = Field(default_factory=list, max_length=2000)


class SnapshotIn(Strict):
    t: float = Field(ge=0, le=86400)
    reason: Literal["two_people", "no_face", "phone", "tab_return"]
    phase: Literal["before", "at", "after"] = "at"
    image: str = Field(min_length=100, max_length=60_000)      # base64 JPEG (data: URL allowed)


class AppealIn(Strict):
    text: str = Field(min_length=5, max_length=4000)
    moments: list[float] = Field(default_factory=list, max_length=50)


class DecisionIn(Strict):
    decision: Literal["confirm", "clear", "need_more"]
    note: str = Field(default="", max_length=2000)


class AppealDecisionIn(Strict):
    outcome: Literal["upheld", "overturned"]
    response: str = Field(min_length=5, max_length=4000)
