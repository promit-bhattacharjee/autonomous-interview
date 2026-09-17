import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.db.models import Base, CredentialVault, StudentProfile, User, UserRole
from src.api.db.session import get_db
from src.api.main import app
from src.api.security.auth import create_access_token, hash_password
from src.api.security.vault import encrypt_api_key
from src.api.services import question_service

# Setup in-memory test database with StaticPool so all connections share the same memory DB
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


class TestSSRAndStaticAssets:
    def test_local_bootstrap_css_served(self):
        response = client.get("/static/vendor/bootstrap/css/bootstrap.min.css")
        assert response.status_code == 200
        assert "bootstrap" in response.text.lower()

    def test_local_bootstrap_js_served(self):
        response = client.get("/static/vendor/bootstrap/js/bootstrap.bundle.min.js")
        assert response.status_code == 200

    def test_login_page_renders_html(self):
        response = client.get("/auth/login")
        assert response.status_code == 200
        assert "Account Login" in response.text


class TestAuthenticationRoutes:
    def test_register_and_login_flow(self):
        # Register student
        reg_data = {
            "username": "student_ukvi",
            "email": "student@ukvi.com",
            "password": "Password123!",
            "full_name": "Rahim Ahmed",
            "device_id": "device-laptop-1",
        }
        reg_res = client.post("/auth/register", data=reg_data, follow_redirects=False)
        assert reg_res.status_code == 303
        assert "access_token" in reg_res.cookies

        # Login with same credentials from a new phone
        login_data = {
            "username": "student_ukvi",
            "password": "Password123!",
            "device_id": "device-phone-2",
        }
        login_res = client.post("/auth/login", data=login_data, follow_redirects=False)
        assert login_res.status_code == 303
        assert "access_token" in login_res.cookies


class TestPreAssignmentGateAndRelationalEndpoints:
    def test_pre_assignment_gate_blocks_token_without_bank(self):
        db = TestingSessionLocal()
        user = User(
            username="candidate1",
            email="cand1@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
            active_device_id="dev-123",
        )
        db.add(user)
        db.commit()

        token = create_access_token(user_id=user.id, role="student", device_id="dev-123")
        client.cookies.set("access_token", token)

        # Pre-interview token check must reject with 403 because no bank is assigned
        res = client.get("/student/token")
        assert res.status_code == 403
        assert "Pre-Assignment Gate" in res.json()["detail"]

        # Interview HTML route redirects to dashboard with error
        interview_res = client.get("/student/interview", follow_redirects=False)
        assert interview_res.status_code == 303

    def test_pre_assignment_gate_allows_interview_and_mints_token_when_bank_assigned(self):
        db = TestingSessionLocal()
        user = User(
            username="candidate2",
            email="cand2@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
            active_device_id="dev-456",
        )
        db.add(user)
        db.flush()

        profile = StudentProfile(user_id=user.id, full_name="Candidate Two")
        db.add(profile)

        bank = question_service.create_question_bank_from_payload(
            db=db,
            title="Intake 2026 Tier 1",
            difficulty="Medium",
            university_id=None,
            topics_payload=[{"name": "Intent", "questions": [{"question_text": "Why UK?"}]}],
        )
        question_service.assign_bank_to_student(db, bank_id=bank.id, student_id=profile.id)
        db.commit()

        token = create_access_token(user_id=user.id, role="student", device_id="dev-456")
        client.cookies.set("access_token", token)

        # Token minting endpoint
        res = client.get("/student/token")
        assert res.status_code == 200
        data = res.json()
        assert "token" in data
        assert data["room_name"] == f"room-{user.id}"
        assert data["bank_title"] == bank.title

        # WebRTC interview HTML screen
        html_res = client.get("/student/interview")
        assert html_res.status_code == 200
        assert "UKVI Credibility Voice Interview" in html_res.text
        assert "livekit-client.umd.min.js" in html_res.text

    def test_student_discard_session_lifecycle_and_reissuance(self):
        db = TestingSessionLocal()
        user = User(
            username="candidate_discard_test",
            email="cand_discard@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
            active_device_id="dev-discard-1",
        )
        db.add(user)
        db.flush()

        profile = StudentProfile(user_id=user.id, full_name="Candidate Discard")
        db.add(profile)

        bank = question_service.create_question_bank_from_payload(
            db=db,
            title="Discard Test Bank",
            difficulty="Medium",
            university_id=None,
            topics_payload=[{"name": "Intent", "questions": [{"question_text": "Why this course?"}]}],
        )
        question_service.assign_bank_to_student(db, bank_id=bank.id, student_id=profile.id)
        db.commit()

        token = create_access_token(user_id=user.id, role="student", device_id="dev-discard-1")
        client.cookies.set("access_token", token)

        # 1. Mint initial token -> session is created in_progress
        res1 = client.get("/student/token")
        assert res1.status_code == 200
        session_id1 = res1.json()["session_id"]

        # 2. Student discards the interview session immediately
        discard_res = client.post("/student/discard", json={"reason": "Candidate dropped connection"})
        assert discard_res.status_code == 200
        discard_data = discard_res.json()
        assert discard_data["status"] == "discarded"
        assert discard_data["session_id"] == session_id1
        assert "elapsed_seconds" in discard_data
        assert "turns_used" in discard_data

        # Verify in DB
        from src.api.db.models import InterviewSessionRecord
        db.expire_all()
        sess_record = db.query(InterviewSessionRecord).filter(InterviewSessionRecord.id == session_id1).first()
        assert sess_record.status == "discarded"
        assert sess_record.concluded_at is not None


        # 3. Student requests a fresh token -> must succeed cleanly without UNIQUE constraint crash
        res2 = client.get("/student/token")
        assert res2.status_code == 200
        data2 = res2.json()
        assert "token" in data2
        assert data2["session_id"] != session_id1


    def test_student_results_viewer_flow(self):
        db = TestingSessionLocal()
        user = User(
            username="candidate3",
            email="cand3@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
            active_device_id="dev-789",
        )
        db.add(user)
        db.flush()

        profile = StudentProfile(user_id=user.id, full_name="Candidate Three", tuition_fee_gbp=15000, available_funds_gbp=30000)
        db.add(profile)

        bank = question_service.create_question_bank_from_payload(
            db=db,
            title="Results Test Bank",
            difficulty="Easy",
            university_id=None,
            topics_payload=[{"name": "General", "questions": [{"question_text": "Q1"}]}],
        )

        from src.api.db.models import InterviewSessionRecord
        session_rec = InterviewSessionRecord(
            student_id=profile.id,
            bank_id=bank.id,
            room_name=f"room-{user.id}",
            status="completed",
            overall_score=88.5,
            ukvi_recommendation="Genuine",
            report_json='{"recommendation": "Candidate meets UKVI standards.", "strengths": ["Clear spoken responses"]}',
        )
        db.add(session_rec)
        db.commit()

        token = create_access_token(user_id=user.id, role="student", device_id="dev-789")
        client.cookies.set("access_token", token)

        res = client.get("/student/results")
        assert res.status_code == 200
        assert "Official UKVI Credibility Report" in res.text
        assert "88.5%" in res.text
        assert "Genuine" in res.text

    def test_admin_bank_tree_editor_and_evaluations(self):
        db = TestingSessionLocal()
        admin_user = User(
            username="admin_lead",
            email="admin@test.com",
            hashed_password=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
            active_device_id="admin-dev-1",
        )
        db.add(admin_user)
        db.flush()

        bank = question_service.create_question_bank_from_payload(
            db=db,
            title="Admin Tree Bank",
            difficulty="Hard",
            university_id=None,
            topics_payload=[
                {
                    "name": "Finance",
                    "questions": [
                        {
                            "question_text": "Show your 28-day bank balance?",
                            "followups": [{"followup_text": "Who is your sponsor?"}],
                        }
                    ],
                }
            ],
        )
        db.commit()

        admin_token = create_access_token(user_id=admin_user.id, role="admin", device_id="admin-dev-1")
        client.cookies.set("access_token", admin_token)

        # 1. View Bank Tree
        tree_res = client.get(f"/admin/banks/{bank.id}")
        assert tree_res.status_code == 200
        assert "Question Bank Tree Editor" in tree_res.text
        assert "Admin Tree Bank" in tree_res.text
        assert "Show your 28-day bank balance?" in tree_res.text

        # 2. Edit Question
        q_record = bank.topics[0].questions[0]
        edit_res = client.post(
            f"/admin/banks/{bank.id}/edit-question",
            data={
                "question_id": q_record.id,
                "question_text": "Updated Question: Show your 28-day bank balance?",
                "expected_time_to_ans": 50,
                "keywords_raw": "funds, balance, maintenance",
            },
            follow_redirects=True,
        )
        assert edit_res.status_code == 200
        assert "Updated Question: Show your 28-day bank balance?" in edit_res.text

        # 3. View Evaluations List
        eval_res = client.get("/admin/evaluations")
        assert eval_res.status_code == 200
        assert "Candidate Credibility Evaluations Audit" in eval_res.text

    def test_relational_endpoints_hierarchy(self):
        db = TestingSessionLocal()
        bank = question_service.create_question_bank_from_payload(
            db=db,
            title="University of Leeds MSc",
            difficulty="Hard",
            university_id=None,
            topics_payload=[
                {
                    "name": "Course Details",
                    "questions": [
                        {
                            "question_text": "What is module 1?",
                            "followups": [{"followup_text": "What does it cover?"}],
                        }
                    ],
                }
            ],
        )

        # 1. Fetch Topics
        topics_res = client.get(f"/api/banks/{bank.id}/topics")
        assert topics_res.status_code == 200
        topics = topics_res.json()
        assert len(topics) == 1
        topic_id = topics[0]["topic_id"]

        # 2. Fetch Questions
        q_res = client.get(f"/api/topics/{topic_id}/questions")
        assert q_res.status_code == 200
        questions = q_res.json()
        assert len(questions) == 1
        q_id = questions[0]["question_id"]

        # 3. Fetch Followups
        f_res = client.get(f"/api/questions/{q_id}/followups")
        assert f_res.status_code == 200
        assert len(f_res.json()) == 1


class TestJWTMiddlewareAndRoleIsolation:
    def test_root_redirects_unauthenticated_to_login(self):
        client.cookies.clear()
        res = client.get("/", follow_redirects=False)
        assert res.status_code == 303
        assert "/auth/login" in res.headers["location"]

    def test_root_redirects_admin_to_admin(self):
        token = create_access_token(user_id="adm-1", role="admin", device_id="dev-1")
        client.cookies.set("access_token", token)
        res = client.get("/", follow_redirects=False)
        assert res.status_code == 303
        assert res.headers["location"] == "/admin"

    def test_root_redirects_student_to_student(self):
        token = create_access_token(user_id="stu-1", role="student", device_id="dev-1")
        client.cookies.set("access_token", token)
        res = client.get("/", follow_redirects=False)
        assert res.status_code == 303
        assert res.headers["location"] == "/student"

    def test_cross_site_student_redirected_from_admin(self):
        token = create_access_token(user_id="stu-1", role="student", device_id="dev-1")
        client.cookies.set("access_token", token)
        # Student visiting /admin is blocked and redirected to /student
        res = client.get("/admin", headers={"accept": "text/html"}, follow_redirects=False)
        assert res.status_code == 303
        assert "/student" in res.headers["location"]

    def test_cross_site_admin_redirected_from_student(self):
        token = create_access_token(user_id="adm-1", role="admin", device_id="dev-1")
        client.cookies.set("access_token", token)
        # Admin visiting /student is blocked and redirected to /admin
        res = client.get("/student", headers={"accept": "text/html"}, follow_redirects=False)
        assert res.status_code == 303
        assert "/admin" in res.headers["location"]

    def test_unauthenticated_blocked_from_admin_and_student(self):
        client.cookies.clear()
        res_admin = client.get("/admin", headers={"accept": "text/html"}, follow_redirects=False)
        assert res_admin.status_code == 303
        assert "/auth/login" in res_admin.headers["location"]

        res_student = client.get("/student", headers={"accept": "text/html"}, follow_redirects=False)
        assert res_student.status_code == 303
        assert "/auth/login" in res_student.headers["location"]

    def test_logged_in_user_redirected_from_login_and_register(self):
        token = create_access_token(user_id="adm-1", role="admin", device_id="dev-1")
        client.cookies.set("access_token", token)
        res_login = client.get("/auth/login", follow_redirects=False)
        assert res_login.status_code == 303
        assert res_login.headers["location"] == "/admin"

        stu_token = create_access_token(user_id="stu-1", role="student", device_id="dev-1")
        client.cookies.set("access_token", stu_token)
        res_reg = client.get("/auth/register", follow_redirects=False)
        assert res_reg.status_code == 303
        assert res_reg.headers["location"] == "/student"


class TestDualLayoutsAndMobileNav:
    def test_student_portal_renders_mobile_bottom_nav_with_interview(self):
        db = TestingSessionLocal()
        user = User(
            username="candidate_nav",
            email="nav@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
            active_device_id="dev-nav",
        )
        db.add(user)
        db.commit()

        token = create_access_token(user_id=user.id, role="student", device_id="dev-nav")
        client.cookies.set("access_token", token)

        res = client.get("/student")
        assert res.status_code == 200
        # Check dedicated student layout markers
        assert "UKVI Candidate Portal" in res.text
        # Check Mobile Bottom Navigation presence and "Interview" item
        assert "mobile-bottom-nav" in res.text
        assert "Interview" in res.text
        assert "/student/interview" in res.text

    def test_admin_portal_renders_command_center_without_mobile_bottom_nav(self):
        db = TestingSessionLocal()
        user = User(
            username="admin_nav",
            email="admin_nav@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.ADMIN,
            active_device_id="dev-admin",
        )
        db.add(user)
        db.commit()

        token = create_access_token(user_id=user.id, role="admin", device_id="dev-admin")
        client.cookies.set("access_token", token)

        res = client.get("/admin")
        assert res.status_code == 200
        # AI Engine Configuration card present
        assert "AI Engine & Model Configuration" in res.text
        # Candidate BYOK cleanup table removed
        assert "Candidate API Key & BYOK Governance" not in res.text
        # Mobile bottom nav should NOT be in admin layout
        assert "mobile-bottom-nav" not in res.text

    def test_admin_can_clean_student_keys_via_route(self):
        db = TestingSessionLocal()
        admin_user = User(
            username="admin_cleaner",
            email="cleaner@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.ADMIN,
            active_device_id="dev-cleaner",
        )
        student_user = User(
            username="student_to_clean",
            email="to_clean@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
            active_device_id="dev-student",
        )
        db.add_all([admin_user, student_user])
        db.commit()

        student_key = CredentialVault(
            user_id=student_user.id,
            category="stt",
            provider="google",
            encrypted_api_key=encrypt_api_key("AIzaSyToCleanKey123"),
            key_preview="AIza...y123",
            is_admin_key=False,
        )
        db.add(student_key)
        db.commit()

        admin_token = create_access_token(user_id=admin_user.id, role="admin", device_id="dev-cleaner")
        client.cookies.set("access_token", admin_token)

        res = client.post(f"/admin/students/{student_user.id}/clean-keys", follow_redirects=False)
        assert res.status_code == 303
        assert res.headers["location"] == "/admin"

        # Verify student key was cleaned in DB
        db.expire_all()
        rem = db.query(CredentialVault).filter(CredentialVault.user_id == student_user.id).first()
        assert rem is None

    def test_candidate_credential_mutation_endpoints_return_403(self):
        db = TestingSessionLocal()
        student_user = User(
            username="candidate_no_keys",
            email="nokeys@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
            active_device_id="dev-stu-nokeys",
        )
        db.add(student_user)
        db.commit()

        student_token = create_access_token(user_id=student_user.id, role="student", device_id="dev-stu-nokeys")
        client.cookies.set("access_token", student_token)

        # HTML Form post endpoint
        res = client.post("/student/credentials", data={"category": "thinking", "provider": "openrouter", "api_key": "sk-attempt"})
        assert res.status_code == 403
        assert "Candidate API key capture is disabled" in res.json()["detail"]

        # BYOK endpoint
        res_byok = client.post("/student/byok", data={"provider": "openrouter", "api_key": "sk-attempt"})
        assert res_byok.status_code == 403

        # API JSON endpoint
        res_api = client.post("/student/api/credentials", json={"category": "thinking", "provider": "openrouter", "api_key": "sk-attempt"})
        assert res_api.status_code == 403


class TestEnvironmentSanitization:
    def test_env_file_has_no_plaintext_api_keys(self):
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("GOOGLE_API_KEY=") or line.startswith("GEMINI_API_KEY=") or line.startswith("OPENROUTER_API_KEY="):
                    val = line.split("=", 1)[1].strip()
                    assert val == "", f"Plaintext key leak found in .env: {line}"


class TestTTSVoiceEndpoint:
    def test_tts_empty_query_param_validation(self):
        res = client.get("/api/tts?text=")
        assert res.status_code in (400, 422)

    def test_tts_audio_synthesis_and_caching(self):
        test_text = "Good morning. Please state your course and university."
        res1 = client.get(f"/api/tts?text={test_text}")
        assert res1.status_code == 200
        assert "audio/mpeg" in res1.headers.get("content-type", "")
        assert len(res1.content) > 1000

        # Second request should be served from memory cache (X-TTS-Cache: HIT)
        res2 = client.get(f"/api/tts?text={test_text}")
        assert res2.status_code == 200
        assert res2.headers.get("X-TTS-Cache") == "HIT"


class TestStaticInstructionAudio:
    def test_static_instruction_audio_asset_exists_and_served(self):
        from pathlib import Path
        audio_path = Path(__file__).resolve().parent.parent / "src" / "api" / "static" / "audio" / "interview_instructions.mp3"
        assert audio_path.exists(), f"Static audio file missing at {audio_path}"
        assert audio_path.stat().st_size > 10000, "Static audio file is unexpectedly small or empty"

        res = client.get("/static/audio/interview_instructions.mp3")
        assert res.status_code == 200
        assert "audio/mpeg" in res.headers.get("content-type", "")
        assert len(res.content) > 10000


class TestInterviewStartingFixes:
    def test_rubric_hits_persistence_in_completed_session(self):
        import json
        from src.api.db.models import InterviewSessionRecord, TurnEvaluationRecord
        db = TestingSessionLocal()
        user = User(
            username="candidate_rubric",
            email="rubric@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
        )
        db.add(user)
        db.flush()

        profile = StudentProfile(user_id=user.id, full_name="Candidate Rubric")
        db.add(profile)
        db.flush()

        bank = question_service.create_question_bank_from_payload(
            db=db,
            title="Rubric Bank",
            difficulty="Medium",
            university_id=None,
            topics_payload=[{"name": "Intent", "questions": [{"question_text": "Why this course?"}]}],
        )
        db.commit()

        sess = InterviewSessionRecord(
            student_id=profile.id,
            bank_id=bank.id,
            room_name=f"room-{user.id}",
            status="in_progress",
        )
        db.add(sess)
        db.commit()

        turns_data = [
            {
                "turn_type": "question",
                "reference_id": "turn-1",
                "spoken_prompt": "Why this course?",
                "candidate_transcript": "I want to study AI at Hertfordshire",
                "score": 85.0,
                "rubric_hits": ["Artificial Intelligence", "Hertfordshire"],
                "missed_keywords": [],
            }
        ]

        completed = question_service.record_completed_session(
            db=db,
            session_id=sess.id,
            overall_score=85.0,
            ukvi_recommendation="Genuine",
            report_data={"recommendation": "Great fit"},
            turns_data=turns_data,
        )
        assert completed.status == "completed"

        # Verify rubric_hits_json is NOT empty
        from src.api.db.models import TurnEvaluationRecord
        saved_turn = db.query(TurnEvaluationRecord).filter(TurnEvaluationRecord.session_id == sess.id).first()
        assert saved_turn is not None
        hits = json.loads(saved_turn.rubric_hits_json)
        assert "Artificial Intelligence" in hits
        assert "Hertfordshire" in hits

    def test_session_resolution_prioritizes_active_session_over_completed(self):
        from src.api.db.models import InterviewSessionRecord
        db = TestingSessionLocal()
        user = User(
            username="candidate_multisess",
            email="multi@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
        )
        db.add(user)
        db.flush()

        profile = StudentProfile(user_id=user.id, full_name="Candidate Multi")
        db.add(profile)
        db.flush()

        bank = question_service.create_question_bank_from_payload(
            db=db,
            title="Multi Bank",
            difficulty="Medium",
            university_id=None,
            topics_payload=[{"name": "Topic", "questions": [{"question_text": "Q1"}]}],
        )
        db.commit()

        # Session 1: Completed previously with same room_name
        sess1 = InterviewSessionRecord(
            student_id=profile.id,
            bank_id=bank.id,
            room_name=f"room-{user.id}",
            status="completed",
            overall_score=90.0,
        )
        db.add(sess1)
        db.commit()

        # Session 2: Currently in_progress
        sess2 = InterviewSessionRecord(
            student_id=profile.id,
            bank_id=bank.id,
            room_name=f"room-{user.id}",
            status="in_progress",
        )
        db.add(sess2)
        db.commit()

        # Call /api/sessions/{user.id}/complete -> must target session 2, NOT session 1
        res = client.post(
            f"/api/sessions/{user.id}/complete",
            json={"overall_score": 75.0, "ukvi_recommendation": "Genuine", "report_data": {}},
        )
        assert res.status_code == 200
        assert res.json()["session_id"] == sess2.id

        db.expire_all()
        reloaded1 = db.query(InterviewSessionRecord).filter(InterviewSessionRecord.id == sess1.id).first()
        reloaded2 = db.query(InterviewSessionRecord).filter(InterviewSessionRecord.id == sess2.id).first()
        assert reloaded1.overall_score == 90.0  # Unchanged!
        assert reloaded2.overall_score == 75.0  # Correctly updated!
        assert reloaded2.status == "completed"


