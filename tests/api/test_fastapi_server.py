import sys
from pathlib import Path
import unittest

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import jwt
from fastapi.testclient import TestClient
from interview.api.server import app
from interview.api.session_store import default_session_store


class TestFastAPIServer(unittest.TestCase):
    """Integration and unit tests for the FastAPI control plane and LiveKit token server."""

    def setUp(self):
        self.client = TestClient(app)
        default_session_store.clear()

    def tearDown(self):
        default_session_store.clear()

    def test_health_check_endpoint(self):
        """Root endpoint returns 200 OK and service status."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "online")
        self.assertEqual(data.get("service"), "UK Credibility Voice Interview API")

    def test_create_session_success(self):
        """Successfully creates an interview session with valid mock API student and university."""
        payload = {
            "student_id": "UK-CAS-2026-9041",
            "university_id": "UK-HERTS-01",
            "difficulty": "Medium",
        }
        response = self.client.post("/api/sessions", json=payload)
        self.assertEqual(response.status_code, 201)

        data = response.json()
        self.assertTrue(data.get("session_id").startswith("session-"))
        self.assertTrue(data.get("room_name").startswith("interview-session-"))
        self.assertEqual(data.get("status"), "created")
        self.assertEqual(data.get("student_id"), "UK-CAS-2026-9041")
        self.assertEqual(data.get("university_id"), "UK-HERTS-01")
        self.assertEqual(data.get("university_name"), "University of Hertfordshire")
        self.assertEqual(data.get("course_name"), "MSc Artificial Intelligence with Advanced Research")

    def test_create_session_invalid_student_returns_404(self):
        """Fails with 404 if student CAS record does not exist."""
        payload = {
            "student_id": "NON-EXISTENT-STUDENT-9999",
            "university_id": "UK-HERTS-01",
        }
        response = self.client.post("/api/sessions", json=payload)
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json().get("detail", "").lower())

    def test_create_session_invalid_university_returns_404(self):
        """Fails with 404 if university ID does not exist."""
        payload = {
            "student_id": "UK-CAS-2026-9041",
            "university_id": "NON-EXISTENT-UNI-9999",
        }
        response = self.client.post("/api/sessions", json=payload)
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json().get("detail", "").lower())

    def test_issue_candidate_token_success(self):
        """Issues valid LiveKit JWT with audio-only microphone grants."""
        # 1. Create a valid session
        create_res = self.client.post(
            "/api/sessions",
            json={"student_id": "UK-CAS-2026-9041", "university_id": "UK-HERTS-01"},
        )
        session_id = create_res.json()["session_id"]
        room_name = create_res.json()["room_name"]

        # 2. Request LiveKit token
        token_res = self.client.post(f"/api/sessions/{session_id}/token")
        self.assertEqual(token_res.status_code, 200)

        token_data = token_res.json()
        self.assertEqual(token_data.get("session_id"), session_id)
        self.assertEqual(token_data.get("room_name"), room_name)
        self.assertEqual(token_data.get("livekit_url"), "ws://127.0.0.1:7880")
        self.assertTrue(len(token_data.get("token", "")) > 20)

        # 3. Decode JWT and assert WebRTC claims
        raw_jwt = token_data["token"]
        decoded = jwt.decode(raw_jwt, options={"verify_signature": False})
        self.assertEqual(decoded.get("sub"), "UK-CAS-2026-9041")
        video_grants = decoded.get("video", {})
        self.assertTrue(video_grants.get("roomJoin"))
        self.assertEqual(video_grants.get("room"), room_name)
        self.assertTrue(video_grants.get("canPublish"))
        self.assertTrue(video_grants.get("canSubscribe"))
        self.assertEqual(video_grants.get("canPublishSources"), ["microphone"])

    def test_issue_token_nonexistent_session_returns_404(self):
        """Fails with 404 if requesting token for non-existent session."""
        response = self.client.post("/api/sessions/session-fake-id-123/token")
        self.assertEqual(response.status_code, 404)

    def test_get_session_metadata(self):
        """Retrieves session metadata by ID."""
        create_res = self.client.post(
            "/api/sessions",
            json={"student_id": "UK-CAS-2026-9041", "university_id": "UK-HERTS-01"},
        )
        session_id = create_res.json()["session_id"]

        get_res = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["session_id"], session_id)

    def test_get_session_status(self):
        """Retrieves real-time session progression and evaluation counts."""
        create_res = self.client.post(
            "/api/sessions",
            json={"student_id": "UK-CAS-2026-9041", "university_id": "UK-HERTS-01"},
        )
        session_id = create_res.json()["session_id"]

        status_res = self.client.get(f"/api/sessions/{session_id}/status")
        self.assertEqual(status_res.status_code, 200)
        data = status_res.json()
        self.assertEqual(data.get("session_id"), session_id)
        self.assertEqual(data.get("interview_status"), "created")
        self.assertEqual(data.get("evaluations_count"), 0)

    def test_get_evaluation_not_completed_returns_400(self):
        """Returns 400 when final evaluation is requested before interview completion."""
        create_res = self.client.post(
            "/api/sessions",
            json={"student_id": "UK-CAS-2026-9041", "university_id": "UK-HERTS-01"},
        )
        session_id = create_res.json()["session_id"]

        eval_res = self.client.get(f"/api/sessions/{session_id}/evaluation")
        self.assertEqual(eval_res.status_code, 400)
        self.assertIn("not been generated", eval_res.json().get("detail", ""))

    def test_livekit_webhook_participant_left(self):
        """LiveKit webhook event triggers session status update to completed."""
        create_res = self.client.post(
            "/api/sessions",
            json={"student_id": "UK-CAS-2026-9041", "university_id": "UK-HERTS-01"},
        )
        session_id = create_res.json()["session_id"]
        room_name = create_res.json()["room_name"]

        webhook_payload = {
            "event": "participant_left",
            "room": {"name": room_name},
            "participant": {"identity": "UK-CAS-2026-9041"},
        }
        res = self.client.post("/api/livekit/webhook", json=webhook_payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "ok")

        # Session should now be marked as completed
        entry = default_session_store.get_session(session_id)
        self.assertEqual(entry.status, "completed")

    def test_cors_headers_present(self):
        """Ensures CORS headers are present for cross-origin frontend requests."""
        response = self.client.options(
            "/api/sessions",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access-control-allow-origin", response.headers)
