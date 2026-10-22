"""Accounts and sessions. Passwords are salted scrypt hashes; a session is a random bearer token. No third-party identity provider, so the demo runs offline."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid

from .store import Store

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(ValueError):
    pass


def _hash(password: str, salt: str) -> str:
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32).hex()


def public(u: dict) -> dict:
    return {"id": u["id"], "name": u["name"], "email": u["email"], "sandbox": bool(u["sandbox"])}


def register(s: Store, name: str, email: str, password: str, now: int, sandbox: bool = False) -> dict:
    name, email = name.strip(), email.strip().lower()
    if len(name) < 2:
        raise AuthError("Tell us your name (at least 2 characters).")
    if not EMAIL.match(email):
        raise AuthError("That email address does not look right.")
    if len(password) < 8:
        raise AuthError("Use a password of at least 8 characters.")
    if s.db.execute("select 1 from users where email=?", (email,)).fetchone():
        raise AuthError("There is already an account with that email. Sign in instead.")
    salt = secrets.token_hex(16)
    u = {"id": "u-" + uuid.uuid4().hex[:10], "email": email, "name": name, "pw": _hash(password, salt), "salt": salt, "sandbox": int(sandbox), "created_ts": now}
    s.insert("users", u)
    return u


def login(s: Store, email: str, password: str) -> dict:
    u = s.one("users", email=email.strip().lower())
    # Same message for "no such user" and "wrong password", and a hash is computed either way.
    ok = hmac.compare_digest(_hash(password, u["salt"] if u else "00" * 16), u["pw"] if u else "0" * 64)
    if not (u and ok) or u["sandbox"]:
        raise AuthError("Wrong email or password.")
    return u


def start_session(s: Store, user_id: str, now: int) -> str:
    token = secrets.token_urlsafe(32)
    s.insert("sessions", {"token": token, "user_id": user_id, "ts": now})
    return token


def user_for(s: Store, token: str | None) -> dict | None:
    if not token:
        return None
    row = s.one("sessions", token=token)
    return s.one("users", id=row["user_id"]) if row else None


def end_session(s: Store, token: str) -> None:
    with s.lock:
        s.db.execute("delete from sessions where token=?", (token,))
        s.db.commit()
