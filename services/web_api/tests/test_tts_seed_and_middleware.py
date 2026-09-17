"""
Unit tests for TTS router, database seeding, and JWT role middleware.
Verifies:
1. /tts endpoint caching and synthesis handling.
2. seed_database idempotent execution.
3. JWTRoleMiddleware access isolation and session token decode.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.db.session import get_db_session, init_db
from src.api.db.seed import seed_database
from src.api.db.models import User, UserRole, QuestionBank
from src.api.routers.tts import router as tts_router, _TTS_CACHE
from src.api.security.auth import create_access_token
from src.api.security.middleware import JWTRoleMiddleware


class TestTTSRouter:
    def test_tts_caching_and_synthesis(self):
        app = FastAPI()
        app.include_router(tts_router)
        client = TestClient(app)

        # 1. Validation check on empty or missing text
        resp_empty = client.get("/tts?text=")
        assert resp_empty.status_code in (400, 422)

        # 2. Mock edge_tts synthesis
        fake_audio = b"FAKE_MP3_AUDIO_STREAM_DATA"
        async def mock_stream(self):
            yield {"type": "audio", "data": fake_audio}

        with patch("edge_tts.Communicate.stream", mock_stream):
            test_phrase = "Welcome to your UKVI interview assessment."
            resp = client.get(f"/tts?text={test_phrase}")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "audio/mpeg"
            assert resp.content == fake_audio

            # 3. Second call should hit the in-memory cache
            resp_cached = client.get(f"/tts?text={test_phrase}")
            assert resp_cached.status_code == 200
            assert resp_cached.headers.get("X-TTS-Cache") == "HIT"
            assert resp_cached.content == fake_audio


class TestDatabaseSeeding:
    def test_seed_database_idempotent(self):
        init_db()
        with get_db_session() as db:
            result1 = seed_database(db)
            assert result1["admin_username"] == "admin"
            assert result1["student_username"] == "student"

            # Check that admin and student users exist
            admin = db.query(User).filter(User.username == "admin").first()
            assert admin is not None
            assert admin.role == UserRole.ADMIN

            student = db.query(User).filter(User.username == "student").first()
            assert student is not None
            assert student.role == UserRole.STUDENT

            # Check that seeded question bank exists
            bank = db.query(QuestionBank).first()
            assert bank is not None
            assert len(bank.topics) >= 1

            # Second execution should succeed without crashing (idempotent)
            result2 = seed_database(db)
            assert result2["admin_username"] == "admin"


class TestJWTRoleMiddleware:
    def test_jwt_role_middleware_isolation(self):
        app = FastAPI()
        app.add_middleware(JWTRoleMiddleware)

        @app.get("/admin/dashboard")
        async def admin_dashboard():
            return {"status": "admin_granted"}

        @app.get("/student/dashboard")
        async def student_dashboard():
            return {"status": "student_granted"}

        @app.get("/login")
        async def login_page():
            return {"page": "login"}

        client = TestClient(app, follow_redirects=False)

        # 1. Unauthenticated student accessing protected student route with text/html header
        resp_unauth = client.get("/student/dashboard", headers={"Accept": "text/html"})
        assert resp_unauth.status_code in (302, 303, 307)
        assert "/login" in resp_unauth.headers.get("location", "")

        # 2. Student token accessing admin route -> redirected or blocked
        student_token = create_access_token(user_id="student_1", role="student", device_id="dev-1")
        client.cookies.set("access_token", student_token)

        resp_student_on_admin = client.get("/admin/dashboard", headers={"Accept": "text/html"})
        # Should redirect to student dashboard
        assert resp_student_on_admin.status_code in (302, 303, 307)
        assert "/student" in resp_student_on_admin.headers.get("location", "")

        # 3. Valid student accessing student route
        resp_student_ok = client.get("/student/dashboard")
        assert resp_student_ok.status_code == 200
        assert resp_student_ok.json() == {"status": "student_granted"}
