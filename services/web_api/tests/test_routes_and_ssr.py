import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.db.models import Base, StudentProfile, User, UserRole
from src.api.db.session import get_db
from src.api.main import app
from src.api.security.auth import create_access_token, hash_password
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
