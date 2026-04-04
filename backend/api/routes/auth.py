import logging
import re

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.api.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


class UserResponse(BaseModel):
    id: int
    email: str


@router.post("/register", response_model=AuthResponse)
async def register(body: AuthRequest, pool: asyncpg.Pool = Depends(get_db)):
    """Create a new user account.

    Validates the email format, hashes the password with bcrypt, and inserts the
    user row. Returns a JWT token alongside the user profile. Returns **409** if
    the email is already registered.
    """
    if not EMAIL_RE.match(body.email):
        raise HTTPException(status_code=422, detail="Invalid email format")
    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    pw_hash = hash_password(body.password)

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id, email",
                body.email.lower().strip(),
                pw_hash,
            )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email already registered")

    token = create_access_token(row["id"], row["email"])
    return {"token": token, "user": {"id": row["id"], "email": row["email"]}}


@router.post("/login", response_model=AuthResponse)
async def login(body: AuthRequest, pool: asyncpg.Pool = Depends(get_db)):
    """Authenticate with email and password.

    Returns a JWT token and user profile on valid credentials. Returns **401**
    if the email is not found or the password does not match.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, password_hash FROM users WHERE email = $1",
            body.email.lower().strip(),
        )

    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(row["id"], row["email"])
    return {"token": token, "user": {"id": row["id"], "email": row["email"]}}


@router.get("/me", response_model=UserResponse)
async def me(user: dict = Depends(get_current_user)):
    """Return the profile of the authenticated user."""
    return {"id": user["id"], "email": user["email"]}
