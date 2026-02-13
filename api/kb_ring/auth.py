import time
from dataclasses import dataclass
from typing import Optional

import jwt

from .config import JWT_SECRET


JWT_ALGORITHM = "HS256"
JWT_ACCESS_EXPIRES_SEC = 3600


@dataclass
class AuthUser:
    user_id: int
    email: str
    display_name: Optional[str] = None


def token_from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    s = authorization.strip()
    if s.lower().startswith("bearer "):
        return s[7:].strip()
    return s.strip()


def create_access_token(user_id: int, email: str, display_name: Optional[str] = None) -> str:
    if not JWT_SECRET:
        return ""
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "name": display_name or email,
        "type": "access",
        "iat": now,
        "exp": now + JWT_ACCESS_EXPIRES_SEC,
    }
    return jwt.encode(payload, JWT_SECRET.encode("utf-8"), algorithm=JWT_ALGORITHM)


def verify_access_token(token: str) -> Optional[AuthUser]:
    if not token or not JWT_SECRET:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET.encode("utf-8"), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        sub = payload.get("sub") or ""
        email = payload.get("email") or ""
        if not sub or not email:
            return None
        return AuthUser(
            user_id=int(sub),
            email=email,
            display_name=payload.get("name"),
        )
    except Exception:
        return None

