import json
from typing import Any, Optional
from sqlalchemy.orm import Session
from src.api.db.models import (
    DifficultyTier,
    FollowupRecord,
    InterviewSessionRecord,
    QuestionAssignment,
    QuestionBank,
    QuestionRecord,
    StudentProfile,
    TopicRecord,
    TurnEvaluationRecord,
)


def get_topics_for_bank(db: Session, bank_id: str) -> list[dict[str, Any]]:
    """Retrieves all topics in sequence for a question bank."""
    topics = (
        db.query(TopicRecord)
        .filter(TopicRecord.bank_id == bank_id)
        .order_by(TopicRecord.order)
        .all()
    )
    return [
        {"topic_id": t.id, "name": t.name, "description": t.description, "order": t.order}
        for t in topics
    ]


def get_questions_for_topic(db: Session, topic_id: str) -> list[dict[str, Any]]:
    """Retrieves all questions in sequence for a specific topic."""
    questions = (
        db.query(QuestionRecord)
        .filter(QuestionRecord.topic_id == topic_id)
        .order_by(QuestionRecord.order)
        .all()
    )
    return [
        {
            "question_id": q.id,
            "question_text": q.question_text,
            "expected_time_to_ans": q.expected_time_to_ans,
            "expected_answer_keywords": json.loads(q.expected_answer_keywords_json),
            "order": q.order,
        }
        for q in questions
    ]


def get_followups_for_question(db: Session, question_id: str) -> list[dict[str, Any]]:
    """Retrieves all follow-up probes for a question."""
    followups = (
        db.query(FollowupRecord)
        .filter(FollowupRecord.question_id == question_id)
        .order_by(FollowupRecord.order)
        .all()
    )
    return [
        {
            "followup_id": f.id,
            "followup_text": f.followup_text,
            "expected_time_to_ans": f.expected_time_to_ans,
            "expected_answer_keywords": json.loads(f.expected_answer_keywords_json),
            "order": f.order,
        }
        for f in followups
    ]


def get_assigned_bank_for_user(db: Session, user_id: str) -> Optional[dict[str, Any]]:
    """
    Resolves the candidate's single active question bank (Pre-Assignment Gate).
    Enforces the rule: One candidate can have at most ONE active assigned question set at a time.
    Returns None if no question set is assigned (blocking interview creation).
    """
    student = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    if not student:
        return None

    # Check for direct candidate assignment first
    assignment = (
        db.query(QuestionAssignment)
        .filter(
            QuestionAssignment.student_id == student.id,
            QuestionAssignment.is_excluded == False,
        )
        .first()
    )

    # Fallback to global assignment if not explicitly excluded
    if not assignment:
        is_excluded = (
            db.query(QuestionAssignment)
            .filter(
                QuestionAssignment.student_id == student.id,
                QuestionAssignment.is_excluded == True,
            )
            .first()
        )
        if not is_excluded:
            assignment = (
                db.query(QuestionAssignment)
                .filter(
                    QuestionAssignment.student_id == None,
                    QuestionAssignment.is_excluded == False,
                )
                .first()
            )

    if not assignment or not assignment.question_bank or not assignment.question_bank.is_active:
        return None

    bank = assignment.question_bank
    return {
        "bank_id": bank.id,
        "title": bank.title,
        "difficulty": bank.difficulty.value,
        "university_id": bank.university_id,
        "topics": get_topics_for_bank(db, bank.id),
    }


def assign_bank_to_student(
    db: Session,
    bank_id: str,
    student_id: Optional[str] = None,
    is_excluded: bool = False,
) -> QuestionAssignment:
    """
    Assigns a QuestionBank to a student or globally.
    Enforces the Auto-Deactivation Invariant:
    If student_id already has an assignment, any previous direct assignment is deleted,
    guaranteeing at most 1 active bank per candidate.
    """
    if student_id:
        # Auto-deactivate prior assignments
        db.query(QuestionAssignment).filter(QuestionAssignment.student_id == student_id).delete()

    assignment = QuestionAssignment(
        bank_id=bank_id,
        student_id=student_id,
        is_excluded=is_excluded,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def create_question_bank_from_payload(
    db: Session,
    title: str,
    difficulty: str,
    university_id: Optional[str],
    topics_payload: list[dict[str, Any]],
    curriculum_source: str = "",
) -> QuestionBank:
    """
    Admin Confirmation Persistence:
    Transactionally commits confirmed topics, questions, and follow-ups to SQLite.
    """
    tier = DifficultyTier(difficulty) if difficulty in DifficultyTier._value2member_map_ else DifficultyTier.MEDIUM
    bank = QuestionBank(
        title=title,
        difficulty=tier,
        university_id=university_id,
        curriculum_source=curriculum_source,
    )
    db.add(bank)
    db.flush()

    for topic_order, topic_data in enumerate(topics_payload, start=1):
        topic = TopicRecord(
            bank_id=bank.id,
            name=topic_data.get("name", f"Topic {topic_order}"),
            description=topic_data.get("description", ""),
            order=topic_order,
        )
        db.add(topic)
        db.flush()

        for q_order, q_data in enumerate(topic_data.get("questions", []), start=1):
            keywords = q_data.get("expected_answer_keywords", [])
            q_record = QuestionRecord(
                topic_id=topic.id,
                question_text=q_data.get("question_text", ""),
                expected_time_to_ans=q_data.get("expected_time_to_ans", 45),
                expected_answer_keywords_json=json.dumps(keywords),
                order=q_order,
            )
            db.add(q_record)
            db.flush()

            for f_order, f_data in enumerate(q_data.get("followups", []), start=1):
                f_keywords = f_data.get("expected_answer_keywords", [])
                f_record = FollowupRecord(
                    question_id=q_record.id,
                    followup_text=f_data.get("followup_text", ""),
                    expected_time_to_ans=f_data.get("expected_time_to_ans", 30),
                    expected_answer_keywords_json=json.dumps(f_keywords),
                    order=f_order,
                )
                db.add(f_record)

    db.commit()
    db.refresh(bank)
    return bank


def get_full_bank_tree(db: Session, bank_id: str) -> Optional[QuestionBank]:
    """Retrieves a question bank with its complete nested topic, question, and follow-up tree."""
    return db.query(QuestionBank).filter(QuestionBank.id == bank_id).first()


def update_question_record(
    db: Session,
    question_id: str,
    question_text: str,
    expected_time_to_ans: int = 45,
    expected_answer_keywords: Optional[list[str]] = None,
) -> Optional[QuestionRecord]:
    """Updates question prompt text, duration limit, and expected keywords."""
    record = db.query(QuestionRecord).filter(QuestionRecord.id == question_id).first()
    if not record:
        return None
    record.question_text = question_text
    record.expected_time_to_ans = expected_time_to_ans
    if expected_answer_keywords is not None:
        record.expected_answer_keywords_json = json.dumps(expected_answer_keywords)
    db.commit()
    db.refresh(record)
    return record


def update_followup_record(
    db: Session,
    followup_id: str,
    followup_text: str,
    expected_time_to_ans: int = 30,
    expected_answer_keywords: Optional[list[str]] = None,
) -> Optional[FollowupRecord]:
    """Updates follow-up probe prompt text, duration limit, and expected keywords."""
    record = db.query(FollowupRecord).filter(FollowupRecord.id == followup_id).first()
    if not record:
        return None
    record.followup_text = followup_text
    record.expected_time_to_ans = expected_time_to_ans
    if expected_answer_keywords is not None:
        record.expected_answer_keywords_json = json.dumps(expected_answer_keywords)
    db.commit()
    db.refresh(record)
    return record


def add_followup_to_question(
    db: Session,
    question_id: str,
    followup_text: str,
    expected_time_to_ans: int = 30,
    expected_answer_keywords: Optional[list[str]] = None,
) -> Optional[FollowupRecord]:
    """Adds a new follow-up probe to an existing question."""
    q_record = db.query(QuestionRecord).filter(QuestionRecord.id == question_id).first()
    if not q_record:
        return None
    order = len(q_record.followups) + 1
    followup = FollowupRecord(
        question_id=question_id,
        followup_text=followup_text,
        expected_time_to_ans=expected_time_to_ans,
        expected_answer_keywords_json=json.dumps(expected_answer_keywords or []),
        order=order,
    )
    db.add(followup)
    db.commit()
    db.refresh(followup)
    return followup


def toggle_bank_active(db: Session, bank_id: str, is_active: bool = True) -> Optional[QuestionBank]:
    """Toggles active/confirmed status of a QuestionBank."""
    bank = db.query(QuestionBank).filter(QuestionBank.id == bank_id).first()
    if not bank:
        return None
    bank.is_active = is_active
    db.commit()
    db.refresh(bank)
    return bank


def record_completed_session(
    db: Session,
    session_id: str,
    overall_score: float,
    ukvi_recommendation: str,
    report_data: dict[str, Any],
    turns_data: Optional[list[dict[str, Any]]] = None,
) -> Optional[InterviewSessionRecord]:
    """
    Persists a normally concluded interview session with overall score,
    UKVI recommendation, full report JSON, and optional turn audit records.
    """
    from datetime import datetime, timezone

    session = db.query(InterviewSessionRecord).filter(InterviewSessionRecord.id == session_id).first()
    if not session:
        return None

    session.status = "completed"
    session.overall_score = overall_score
    session.ukvi_recommendation = ukvi_recommendation
    session.report_json = json.dumps(report_data)
    session.concluded_at = datetime.now(timezone.utc)

    if turns_data:
        for t in turns_data:
            turn_record = TurnEvaluationRecord(
                session_id=session.id,
                turn_type=t.get("turn_type", "question"),
                reference_id=t.get("reference_id", "q-unknown"),
                spoken_prompt=t.get("spoken_prompt", ""),
                candidate_transcript=t.get("candidate_transcript", ""),
                score=float(t.get("score", 0.0)),
                rubric_hits_json=json.dumps(t.get("matched_keywords", [])),
                missed_keywords_json=json.dumps(t.get("missed_keywords", [])),
                latency_ms=int(t.get("latency_ms", 0)),
            )
            db.add(turn_record)

    db.commit()
    db.refresh(session)
    return session
