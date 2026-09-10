import json
from typing import Any, Optional
from sqlalchemy.orm import Session
from src.api.db.models import (
    DifficultyTier,
    FollowupRecord,
    QuestionAssignment,
    QuestionBank,
    QuestionRecord,
    StudentProfile,
    TopicRecord,
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
