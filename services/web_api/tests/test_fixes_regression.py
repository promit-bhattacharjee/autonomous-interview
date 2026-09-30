import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.db.models import Base, CredentialVault, FollowupRecord, QuestionBank, QuestionRecord, TopicRecord, User, UserRole
from src.api.security.vault import encrypt_api_key, mask_api_key
from src.api.services import question_service, vault_service
from services.langgraph_agent.src.agent.guard import abort_and_discard_session
from services.langgraph_agent.src.agent.prompts.rubrics import evaluate_response_keywords


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


class TestFixesRegression:
    def test_rubrics_word_boundary_regex(self):
        """Validates that short words like 'in' or 'art' do not match inside larger words."""
        # Candidate says 'training start', but expected keywords are 'in' and 'art'
        score, hits, missed = evaluate_response_keywords("training start", ["in", "art"])
        assert hits == []
        assert set(missed) == {"in", "art"}
        assert score == 0.0

        # Exact match should succeed
        score, hits, missed = evaluate_response_keywords("I enrolled in state of the art facilities", ["in", "art"])
        assert set(hits) == {"in", "art"}
        assert missed == []
        assert score == 100.0

    def test_question_service_handles_none_keywords(self, db_session):
        """Validates that question_service does not raise TypeError when keywords JSON is None."""
        bank = QuestionBank(title="Test Bank")
        db_session.add(bank)
        db_session.commit()

        topic = TopicRecord(bank_id=bank.id, name="Topic 1")
        db_session.add(topic)
        db_session.commit()

        q = QuestionRecord(
            topic_id=topic.id,
            question_text="Sample Q",
            expected_answer_keywords_json=None,
        )
        db_session.add(q)
        db_session.commit()

        f = FollowupRecord(
            question_id=q.id,
            followup_text="Sample F",
            expected_answer_keywords_json=None,
        )
        db_session.add(f)
        db_session.commit()

        questions = question_service.get_questions_for_topic(db_session, topic.id)
        assert len(questions) == 1
        assert questions[0]["expected_answer_keywords"] == []

        followups = question_service.get_followups_for_question(db_session, q.id)
        assert len(followups) == 1
        assert followups[0]["expected_answer_keywords"] == []

    def test_vault_service_preserves_existing_key_on_masked_preview(self, db_session):
        """Validates that submitting masked key preview sk-...xxxx does not overwrite the secret."""
        real_key = "sk-live-super-secret-key-12345"
        vault_service.save_model_credential(
            db=db_session,
            category="thinking",
            provider="openrouter",
            api_key=real_key,
            model_name="deepseek/deepseek-v4",
            is_admin=True,
        )

        entry = db_session.query(CredentialVault).filter(CredentialVault.category == "thinking").first()
        initial_encrypted = entry.encrypted_api_key
        assert entry.key_preview == mask_api_key(real_key)

        # Update model name while passing masked preview in form
        vault_service.save_model_credential(
            db=db_session,
            category="thinking",
            provider="openrouter",
            api_key=entry.key_preview,  # e.g. sk-...2345
            model_name="deepseek/deepseek-v4-updated",
            is_admin=True,
        )

        db_session.refresh(entry)
        assert entry.model_name == "deepseek/deepseek-v4-updated"
        # Secret key should NOT have been overwritten
        assert entry.encrypted_api_key == initial_encrypted

    def test_discard_guard_safe_json_with_quotes(self, db_session):
        """Validates that reason with quotes does not break JSON serialization."""
        from src.api.db.models import InterviewSessionRecord
        bank = QuestionBank(title="Bank")
        db_session.add(bank)
        db_session.commit()

        profile_user = User(
            username="stud1",
            email="s1@test.com",
            hashed_password="pw",
            role=UserRole.STUDENT,
        )
        db_session.add(profile_user)
        db_session.commit()

        from src.api.db.models import StudentProfile
        sp = StudentProfile(user_id=profile_user.id, full_name="Student 1")
        db_session.add(sp)
        db_session.commit()

        session = InterviewSessionRecord(
            student_id=sp.id,
            bank_id=bank.id,
            room_name="room-stud1",
            status="in_progress",
        )
        db_session.add(session)
        db_session.commit()

        tricky_reason = 'Candidate said: "I want to abort now!" and newline\n'
        abort_and_discard_session(db=db_session, session_id="room-stud1", reason=tricky_reason)

        db_session.refresh(session)
        assert session.status == "discarded"
        parsed = json.loads(session.report_json)
        assert parsed["discard_reason"] == tricky_reason

    def test_admin_evaluation_detail_route(self, db_session):
        """Validates that GET /admin/evaluations/{session_id} renders candidate scorecard."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.api.db.session import get_db
        from src.api.db.models import InterviewSessionRecord, StudentProfile, TurnEvaluationRecord
        from src.api.security.auth import create_access_token

        def override_db():
            yield db_session

        prior_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = override_db
        try:
            client = TestClient(app)

            admin = User(username="admin_test", email="adm@test.com", hashed_password="pw", role=UserRole.ADMIN, active_device_id="dev-1")
            student = User(username="stud_eval", email="eval@test.com", hashed_password="pw", role=UserRole.STUDENT, active_device_id="dev-2")
            db_session.add_all([admin, student])
            db_session.commit()

            sp = StudentProfile(user_id=student.id, full_name="Amina Begum", academic_background="BSc CS")
            bank = QuestionBank(title="Hertfordshire MSc AI")
            db_session.add_all([sp, bank])
            db_session.commit()

            sess = InterviewSessionRecord(
                student_id=sp.id,
                bank_id=bank.id,
                room_name="room-stud_eval",
                status="completed",
                overall_score=85.5,
                ukvi_recommendation="Genuine",
                report_json=json.dumps({"recommendation": "Candidate demonstrated strong genuine intent."}),
            )
            db_session.add(sess)
            db_session.commit()

            turn = TurnEvaluationRecord(
                session_id=sess.id,
                turn_type="question",
                reference_id="q1",
                spoken_prompt="Why Hertfordshire?",
                candidate_transcript="Because of the specialized curriculum modules.",
                score=90.0,
            )
            db_session.add(turn)
            db_session.commit()

            admin_token = create_access_token(user_id=admin.id, role="admin", device_id="dev-1")
            client.cookies.set("access_token", admin_token)

            res = client.get(f"/admin/evaluations/{sess.id}")
            assert res.status_code == 200
            assert "Amina Begum" in res.text
            assert "85.5%" in res.text
            assert "Why Hertfordshire?" in res.text
            assert "Because of the specialized curriculum modules." in res.text
        finally:
            if prior_override is not None:
                app.dependency_overrides[get_db] = prior_override
            else:
                app.dependency_overrides.pop(get_db, None)

    def test_admin_bank_generate_synthesizes_topics(self, db_session):
        """Validates that POST /admin/banks/generate runs synthesis graph to formulate 3 modules."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.api.db.session import get_db
        from src.api.security.auth import create_access_token

        def override_db():
            yield db_session

        prior_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = override_db
        try:
            client = TestClient(app)

            admin = User(username="admin_gen", email="adm_gen@test.com", hashed_password="pw", role=UserRole.ADMIN, active_device_id="dev-gen")
            db_session.add(admin)
            db_session.commit()

            admin_token = create_access_token(user_id=admin.id, role="admin", device_id="dev-gen")
            client.cookies.set("access_token", admin_token)

            res = client.post("/admin/banks/generate", data={
                "title": "MSc Robotics",
                "difficulty": "Hard",
                "curriculum_text": "Autonomous systems and mobile robotics.",
            }, follow_redirects=False)

            assert res.status_code == 303
            created_bank = db_session.query(QuestionBank).filter(QuestionBank.title == "MSc Robotics").first()
            assert created_bank is not None
            assert len(created_bank.topics) == 3
            # Hard tier should set 60s limit
            assert created_bank.topics[0].questions[0].expected_time_to_ans == 60
        finally:
            if prior_override is not None:
                app.dependency_overrides[get_db] = prior_override
            else:
                app.dependency_overrides.pop(get_db, None)

    def test_record_completed_session_idempotent_turns(self, db_session):
        """Validates that completing a session multiple times does not duplicate turn evaluations."""
        from src.api.db.models import InterviewSessionRecord, StudentProfile, TurnEvaluationRecord
        admin = User(username="admin_idem", email="idem@test.com", hashed_password="pw", role=UserRole.ADMIN)
        student = User(username="stud_idem", email="s_idem@test.com", hashed_password="pw", role=UserRole.STUDENT)
        db_session.add_all([admin, student])
        db_session.commit()

        sp = StudentProfile(user_id=student.id, full_name="Student Idem")
        bank = QuestionBank(title="Bank Idem")
        db_session.add_all([sp, bank])
        db_session.commit()

        sess = InterviewSessionRecord(
            student_id=sp.id,
            bank_id=bank.id,
            room_name="room-stud_idem",
            status="in_progress",
        )
        db_session.add(sess)
        db_session.commit()

        sample_turns = [
            {"turn_type": "question", "reference_id": "q1", "spoken_prompt": "Q1", "candidate_transcript": "A1", "score": 80.0},
            {"turn_type": "followup", "reference_id": "f1", "spoken_prompt": "F1", "candidate_transcript": "A2", "score": 85.0},
        ]

        # Call completion first time
        question_service.record_completed_session(
            db=db_session,
            session_id=sess.id,
            overall_score=82.5,
            ukvi_recommendation="Genuine",
            report_data={"summary": "Pass"},
            turns_data=sample_turns,
        )
        turns_count_1 = db_session.query(TurnEvaluationRecord).filter(TurnEvaluationRecord.session_id == sess.id).count()
        assert turns_count_1 == 2

        # Call completion second time (retry scenario)
        question_service.record_completed_session(
            db=db_session,
            session_id=sess.id,
            overall_score=82.5,
            ukvi_recommendation="Genuine",
            report_data={"summary": "Pass"},
            turns_data=sample_turns,
        )
        turns_count_2 = db_session.query(TurnEvaluationRecord).filter(TurnEvaluationRecord.session_id == sess.id).count()
        assert turns_count_2 == 2  # Idempotent: exactly 2, not 4

    def test_abort_and_discard_session_sets_concluded_at(self, db_session):
        """Validates that abort_and_discard_session records concluded_at timestamp."""
        from src.api.db.models import InterviewSessionRecord, StudentProfile
        student = User(username="stud_disc", email="s_disc@test.com", hashed_password="pw", role=UserRole.STUDENT)
        db_session.add(student)
        db_session.commit()

        sp = StudentProfile(user_id=student.id, full_name="Student Discard")
        bank = QuestionBank(title="Bank Discard")
        db_session.add_all([sp, bank])
        db_session.commit()

        sess = InterviewSessionRecord(
            student_id=sp.id,
            bank_id=bank.id,
            room_name="room-stud_disc",
            status="in_progress",
        )
        db_session.add(sess)
        db_session.commit()

        assert sess.concluded_at is None
        abort_and_discard_session(db=db_session, session_id=sess.id, reason="Lost connection")
        db_session.refresh(sess)
        assert sess.status == "discarded"
        assert sess.concluded_at is not None

    def test_toggle_bank_status_prevents_open_redirect(self, db_session):
        """Validates that toggle_bank_status rejects external Referer headers to prevent open redirects."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.api.db.session import get_db
        from src.api.security.auth import create_access_token

        def override_db():
            yield db_session

        prior_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = override_db
        try:
            client = TestClient(app)
            admin = User(username="admin_redir", email="redir@test.com", hashed_password="pw", role=UserRole.ADMIN, active_device_id="dev-redir")
            bank = QuestionBank(title="Bank Redir", is_active=True)
            db_session.add_all([admin, bank])
            db_session.commit()

            admin_token = create_access_token(user_id=admin.id, role="admin", device_id="dev-redir")
            client.cookies.set("access_token", admin_token)

            # Malicious external Referer
            res = client.post(
                f"/admin/banks/{bank.id}/toggle-active",
                data={"is_active": "false"},
                headers={"Referer": "https://attacker.evil.com/phishing"},
                follow_redirects=False,
            )
            assert res.status_code == 303
            # Must redirect safely to internal bank URL, NOT attacker site
            assert res.headers["location"] == f"/admin/banks/{bank.id}"
        finally:
            if prior_override is not None:
                app.dependency_overrides[get_db] = prior_override
            else:
                app.dependency_overrides.pop(get_db, None)

    def test_assign_bank_to_student_sanitizes_blank_student_id(self, db_session):
        """Validates that assigning bank with an empty string student_id is sanitized to None (global assignment)."""
        bank = QuestionBank(title="Bank Global")
        db_session.add(bank)
        db_session.commit()

        assignment = question_service.assign_bank_to_student(db_session, bank_id=bank.id, student_id="   ")
        assert assignment.student_id is None
        assert assignment.bank_id == bank.id

    def test_student_results_and_admin_detail_render_robustly(self, db_session):
        """Validates that student results and admin detail render cleanly when turns have None scores or discarded status."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.api.db.session import get_db
        from src.api.security.auth import create_access_token
        from src.api.db.models import InterviewSessionRecord, StudentProfile, TurnEvaluationRecord

        def override_db():
            yield db_session

        prior_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = override_db
        try:
            client = TestClient(app)
            student = User(username="stud_robust", email="robust@test.com", hashed_password="pw", role=UserRole.STUDENT, active_device_id="dev-robust")
            admin = User(username="admin_robust", email="adm_robust@test.com", hashed_password="pw", role=UserRole.ADMIN, active_device_id="dev-adm-robust")
            db_session.add_all([student, admin])
            db_session.commit()

            sp = StudentProfile(user_id=student.id, full_name="Student Robust")
            bank = QuestionBank(title="Bank Robust")
            db_session.add_all([sp, bank])
            db_session.commit()

            sess = InterviewSessionRecord(
                student_id=sp.id,
                bank_id=bank.id,
                room_name="room-stud_robust",
                status="completed",
                overall_score=78.5,
                ukvi_recommendation="Genuine",
            )
            db_session.add(sess)
            db_session.commit()

            # Add turn with score=None
            turn = TurnEvaluationRecord(
                session_id=sess.id,
                turn_type="question",
                reference_id="q-1",
                spoken_prompt="Why study in the UK?",
                candidate_transcript="I want quality education.",
                score=None,
            )
            db_session.add(turn)
            db_session.commit()

            # Verify student results page does not throw TypeError on None score
            stud_token = create_access_token(user_id=student.id, role="student", device_id="dev-robust")
            client.cookies.set("access_token", stud_token)
            res_stud = client.get(f"/student/results/{sess.id}")
            assert res_stud.status_code == 200
            assert "Official UKVI Credibility Report" in res_stud.text

            # Verify admin evaluation detail page also renders cleanly
            adm_token = create_access_token(user_id=admin.id, role="admin", device_id="dev-adm-robust")
            client.cookies.set("access_token", adm_token)
            res_adm = client.get(f"/admin/evaluations/{sess.id}")
            assert res_adm.status_code == 200
            assert "Candidate Credibility Evaluation" in res_adm.text
        finally:
            if prior_override is not None:
                app.dependency_overrides[get_db] = prior_override
            else:
                app.dependency_overrides.pop(get_db, None)

