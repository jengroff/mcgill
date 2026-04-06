from __future__ import annotations

import uuid

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.auth import (
    create_access_token,
    hash_password,
    verify_password,
)
from backend.config import settings
from tests.conftest import requires_postgres


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest_asyncio.fixture
async def clean_users(db: asyncpg.Pool):
    """Delete test users before and after each test."""
    await db.execute("DELETE FROM messages")
    await db.execute("DELETE FROM conversations")
    await db.execute("DELETE FROM users WHERE email LIKE '%@test.mcgill%'")
    yield
    await db.execute("DELETE FROM messages")
    await db.execute("DELETE FROM conversations")
    await db.execute("DELETE FROM users WHERE email LIKE '%@test.mcgill%'")


def _unique_email() -> str:
    return f"{uuid.uuid4().hex[:8]}@test.mcgill"


# ---------------------------------------------------------------------------
# Unit tests — password hashing
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "mysecretpassword"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt salts differ
        assert verify_password("same", h1)
        assert verify_password("same", h2)


# ---------------------------------------------------------------------------
# Unit tests — JWT tokens
# ---------------------------------------------------------------------------


class TestJWT:
    def test_create_and_decode(self):
        import jwt

        token = create_access_token(42, "user@test.mcgill")
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert payload["sub"] == "42"
        assert payload["email"] == "user@test.mcgill"
        assert "exp" in payload

    @requires_postgres
    def test_expired_token(self):
        import jwt
        from datetime import datetime, timedelta, timezone

        payload = {
            "sub": "1",
            "email": "expired@test.mcgill",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = jwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )

        app = create_app()
        with TestClient(app) as c:
            resp = c.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 401

    @requires_postgres
    def test_invalid_token(self):
        app = create_app()
        with TestClient(app) as c:
            resp = c.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer garbage.token.here"},
            )
            assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Integration tests — /api/v1/auth endpoints
# ---------------------------------------------------------------------------


@requires_postgres
class TestRegister:
    def test_register_returns_token_and_user(self, client, clean_users):
        email = _unique_email()
        resp = client.post(
            "/api/v1/auth/register",
            json={"name": "Test User", "email": email, "password": "validpass1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["email"] == email
        assert isinstance(data["user"]["id"], int)

    def test_register_duplicate_email_409(self, client, clean_users):
        email = _unique_email()
        client.post(
            "/api/v1/auth/register",
            json={"name": "Test User", "email": email, "password": "validpass1"},
        )
        resp = client.post(
            "/api/v1/auth/register",
            json={"name": "Test User", "email": email, "password": "validpass1"},
        )
        assert resp.status_code == 409

    def test_register_invalid_email_422(self, client, clean_users):
        resp = client.post(
            "/api/v1/auth/register",
            json={"name": "Test", "email": "not-an-email", "password": "validpass1"},
        )
        assert resp.status_code == 422

    def test_register_short_password_422(self, client, clean_users):
        resp = client.post(
            "/api/v1/auth/register",
            json={"name": "Test", "email": _unique_email(), "password": "short"},
        )
        assert resp.status_code == 422

    def test_register_email_normalized_lowercase(self, client, clean_users):
        email = _unique_email()
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "name": "Test User",
                "email": email.upper(),
                "password": "validpass1",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == email.lower()


@requires_postgres
class TestLogin:
    def test_login_valid_credentials(self, client, clean_users):
        email = _unique_email()
        client.post(
            "/api/v1/auth/register",
            json={"name": "Test User", "email": email, "password": "validpass1"},
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"name": "Test User", "email": email, "password": "validpass1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["email"] == email

    def test_login_wrong_password_401(self, client, clean_users):
        email = _unique_email()
        client.post(
            "/api/v1/auth/register",
            json={"name": "Test User", "email": email, "password": "validpass1"},
        )
        resp = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrongpass1"}
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user_401(self, client, clean_users):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@test.mcgill", "password": "validpass1"},
        )
        assert resp.status_code == 401


@requires_postgres
class TestMe:
    def test_me_authenticated(self, client, clean_users):
        email = _unique_email()
        reg = client.post(
            "/api/v1/auth/register",
            json={"name": "Test User", "email": email, "password": "validpass1"},
        )
        token = reg.json()["token"]
        resp = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == email

    def test_me_no_token_401(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_bad_token_401(self, client):
        resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Integration tests — authenticated chat persistence
# ---------------------------------------------------------------------------


@requires_postgres
class TestChatPersistence:
    def _register(self, client) -> tuple[str, str]:
        email = _unique_email()
        reg = client.post(
            "/api/v1/auth/register",
            json={"name": "Test User", "email": email, "password": "validpass1"},
        )
        return reg.json()["token"], email

    def test_authenticated_session_creates_conversation(self, client, clean_users):
        token, _ = self._register(client)
        resp = client.post(
            "/api/v1/chat/session",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        convos = client.get(
            "/api/v1/chat/conversations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert convos.status_code == 200
        ids = [c["session_id"] for c in convos.json()]
        assert session_id in ids

    def test_ask_persists_user_message(self, client, clean_users):
        token, _ = self._register(client)
        session = client.post(
            "/api/v1/chat/session",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        sid = session.json()["session_id"]

        client.post(
            "/api/v1/chat/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "What is COMP 251?", "session_id": sid},
        )

        msgs = client.get(
            f"/api/v1/chat/conversations/{sid}/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert msgs.status_code == 200
        assert len(msgs.json()) >= 1
        assert msgs.json()[0]["role"] == "user"
        assert msgs.json()[0]["content"] == "What is COMP 251?"

    def test_conversation_title_auto_generated(self, client, clean_users):
        token, _ = self._register(client)
        session = client.post(
            "/api/v1/chat/session",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        sid = session.json()["session_id"]

        client.post(
            "/api/v1/chat/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "message": "Tell me about artificial intelligence courses",
                "session_id": sid,
            },
        )

        convos = client.get(
            "/api/v1/chat/conversations",
            headers={"Authorization": f"Bearer {token}"},
        )
        convo = next(c for c in convos.json() if c["session_id"] == sid)
        assert "artificial intelligence" in convo["title"].lower()

    def test_anonymous_session_works_without_persistence(self, client, clean_users):
        resp = client.post("/api/v1/chat/session", json={})
        assert resp.status_code == 200
        sid = resp.json()["session_id"]

        resp = client.post(
            "/api/v1/chat/ask",
            json={"message": "Hello!", "session_id": sid},
        )
        assert resp.status_code == 200

    def test_conversations_endpoint_requires_auth(self, client):
        resp = client.get("/api/v1/chat/conversations")
        assert resp.status_code == 401

    def test_messages_endpoint_requires_auth(self, client):
        resp = client.get("/api/v1/chat/conversations/fake-id/messages")
        assert resp.status_code == 401

    def test_session_resume_loads_messages(self, client, clean_users):
        token, _ = self._register(client)

        # Create session and send a message
        session = client.post(
            "/api/v1/chat/session",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        sid = session.json()["session_id"]

        client.post(
            "/api/v1/chat/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "First message", "session_id": sid},
        )

        # Resume the session
        resumed = client.post(
            "/api/v1/chat/session",
            headers={"Authorization": f"Bearer {token}"},
            json={"session_id": sid},
        )
        assert resumed.status_code == 200
        assert resumed.json()["session_id"] == sid

    def test_other_users_conversation_returns_404(self, client, clean_users):
        token1, _ = self._register(client)
        token2, _ = self._register(client)

        # User 1 creates a session
        session = client.post(
            "/api/v1/chat/session",
            headers={"Authorization": f"Bearer {token1}"},
            json={},
        )
        sid = session.json()["session_id"]

        # User 2 tries to access User 1's messages
        resp = client.get(
            f"/api/v1/chat/conversations/{sid}/messages",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert resp.status_code == 404
