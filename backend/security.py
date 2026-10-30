"""Password / login-code hashing (stdlib scrypt) and JWT access tokens."""
import base64
import hashlib
import hmac
import secrets

_N, _R, _P = 2 ** 14, 8, 1
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I/L: easy to read out on a phone


def hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(secret.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_secret(secret: str, stored: str) -> bool:
    try:
        _, salt, dk = stored.split("$")
        got = hashlib.scrypt(secret.encode(), salt=base64.b64decode(salt), n=_N, r=_R, p=_P, dklen=32)
        return hmac.compare_digest(got, base64.b64decode(dk))
    except Exception:
        return False


def new_login_code(n: int = 6) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(n))


def new_join_code() -> str:
    return "FP-" + new_login_code(6)


def new_session_id(prefix: str = "L") -> str:
    return prefix + "-" + secrets.token_hex(5).upper()


# ---------------------------------------------------------------- JWT (HS256, PyJWT)
def make_jwt(user: dict, secret: str, hours: int) -> tuple[str, str, str]:
    """Returns (token, jti, expires_at ISO)."""
    import datetime as dt

    import jwt
    now = dt.datetime.now(dt.timezone.utc)
    exp = now + dt.timedelta(hours=hours)
    jti = secrets.token_hex(12)
    token = jwt.encode({"sub": str(user["id"]), "role": user["role"], "name": user["name"], "jti": jti,
                        "tv": int(user.get("token_version") or 0),      # bumped when the password changes
                        "iat": int(now.timestamp()), "exp": int(exp.timestamp())}, secret, algorithm="HS256")
    return token, jti, exp.strftime("%Y-%m-%dT%H:%M:%SZ")


def read_jwt(token: str, secret: str) -> dict | None:
    import jwt
    try:
        return jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["sub", "exp", "jti"]})
    except jwt.PyJWTError:
        return None
