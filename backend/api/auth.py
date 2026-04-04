import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, Request

from backend.config import settings

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(user_id: int, email: str, name: str = "") -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "name": name,
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def _decode_token(token: str) -> dict:
    return jwt.decode(
        token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
    )


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    return auth[7:]


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency that extracts and validates a JWT from the Authorization header.

    Returns a dict with `id`, `email`, and `name` keys. Raises **401** if the
    token is missing, expired, or otherwise invalid.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    try:
        payload = _decode_token(token)
        return {
            "id": int(payload["sub"]),
            "email": payload["email"],
            "name": payload.get("name", ""),
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid authentication token")


async def get_optional_user(request: Request) -> dict | None:
    """Same as `get_current_user` but returns **None** when no token is present
    instead of raising. Useful for endpoints that work both authenticated and
    anonymous.
    """
    token = _extract_token(request)
    if not token:
        return None
    try:
        payload = _decode_token(token)
        return {
            "id": int(payload["sub"]),
            "email": payload["email"],
            "name": payload.get("name", ""),
        }
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
