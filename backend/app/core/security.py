import hashlib
from datetime import datetime, timedelta, timezone
import jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(raw: str) -> str:
    return pwd_ctx.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return pwd_ctx.verify(raw, hashed)
    except Exception:
        return False


def _token(sub: str, kind: str, expires_delta: timedelta, extra: dict | None = None) -> str:
    payload = {
        "sub": sub,
        "typ": kind,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def pwd_fingerprint(password_hash: str) -> str:
    """Short, non-reversible marker of the current password. Embedded in tokens so
    that changing a password (or an admin reset) immediately invalidates every
    token issued before it."""
    return hashlib.sha256((password_hash or "").encode()).hexdigest()[:12]


def create_access_token(user_id: int, extra: dict | None = None) -> str:
    return _token(str(user_id), "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), extra)


def create_refresh_token(user_id: int, extra: dict | None = None) -> str:
    return _token(str(user_id), "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), extra)


def decode_token(token: str, expected_type: str = "access") -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token")
    return payload
