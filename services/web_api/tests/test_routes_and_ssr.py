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
    def test_pre_assignment_gate_blocks_interview_without_bank(self):
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

        # Pre-interview check must reject with 403 because no bank is assigned
        res = client.get("/student/interview")
        assert res.status_code == 403
        assert "Pre-Assignment Gate" in res.json()["detail"]

    def test_pre_assignment_gate_allows_interview_when_bank_assigned(self):
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

        res = client.get("/student/interview")
        assert res.status_code == 200
        assert res.json()["status"] == "ready"
        assert res.json()["bank_id"] == bank.id

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
