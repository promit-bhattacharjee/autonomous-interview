import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from src.api.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    STUDENT = "student"


class DifficultyTier(str, enum.Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"


class ModelCategory(str, enum.Enum):
    THINKING = "thinking"
    STT = "stt"
    TTS = "tts"


class AIProvider(str, enum.Enum):
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    DEEPGRAM = "deepgram"
    ELEVENLABS = "elevenlabs"
    CARTESIA = "cartesia"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"
    GLM = "glm"
    GROQ = "groq"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.STUDENT, nullable=False)
    active_device_id = Column(String(128), nullable=True)  # Single-device session lockdown
    last_login_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    student_profile = relationship("StudentProfile", back_populates="user", uselist=False)
    credentials = relationship("CredentialVault", back_populates="user", cascade="all, delete-orphan")


class University(Base):
    __tablename__ = "universities"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    university_code = Column(String(50), unique=True, nullable=False, index=True)
    official_name = Column(String(200), nullable=False)
    campus_location = Column(String(200), nullable=False)
    tuition_fee_gbp = Column(Float, nullable=False, default=0.0)
    living_cost_guideline_gbp = Column(Float, nullable=False, default=0.0)
    target_course = Column(String(200), nullable=False)
    degree_level = Column(String(50), default="Postgraduate", nullable=False)
    duration_months = Column(Integer, default=12, nullable=False)
    core_modules_json = Column(Text, default="[]", nullable=False)
    campus_facilities_json = Column(Text, default="[]", nullable=False)
    competitor_differentiators_json = Column(Text, default="[]", nullable=False)
    compliance_rubrics_json = Column(Text, default="[]", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    students = relationship("StudentProfile", back_populates="selected_university")
    question_banks = relationship("QuestionBank", back_populates="university")


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    selected_university_id = Column(String(36), ForeignKey("universities.id"), nullable=True)
    full_name = Column(String(150), nullable=False)
    academic_background = Column(Text, default="", nullable=False)
    english_proficiency = Column(String(100), default="", nullable=False)
    tuition_fee_gbp = Column(Float, default=0.0, nullable=False)
    living_cost_gbp = Column(Float, default=0.0, nullable=False)
    available_funds_gbp = Column(Float, default=0.0, nullable=False)
    sponsor_details = Column(Text, default="", nullable=False)
    post_study_plan = Column(Text, default="", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="student_profile")
    selected_university = relationship("University", back_populates="students")
    assignments = relationship("QuestionAssignment", back_populates="student")
    sessions = relationship("InterviewSessionRecord", back_populates="student")


class CredentialVault(Base):
    __tablename__ = "credential_vault"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)  # Null for system/admin key
    category = Column(String(50), default=ModelCategory.THINKING.value, nullable=False)  # thinking, stt, tts
    provider = Column(String(50), nullable=False)  # openrouter, google, openai, etc.
    model_name = Column(String(120), nullable=True)
    base_url = Column(String(255), nullable=True)
    voice = Column(String(50), nullable=True)
    encrypted_api_key = Column(Text, nullable=False)
    key_preview = Column(String(20), nullable=False)
    is_admin_key = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="credentials")


class QuestionBank(Base):
    __tablename__ = "question_banks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    university_id = Column(String(36), ForeignKey("universities.id"), nullable=True)
    title = Column(String(200), nullable=False)
    difficulty = Column(Enum(DifficultyTier), default=DifficultyTier.MEDIUM, nullable=False)
    curriculum_source = Column(Text, default="")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    university = relationship("University", back_populates="question_banks")
    topics = relationship("TopicRecord", back_populates="bank", cascade="all, delete-orphan")
    assignments = relationship("QuestionAssignment", back_populates="question_bank", cascade="all, delete-orphan")


class TopicRecord(Base):
    __tablename__ = "topic_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    bank_id = Column(String(36), ForeignKey("question_banks.id"), nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(Text, default="")
    order = Column(Integer, default=1, nullable=False)

    bank = relationship("QuestionBank", back_populates="topics")
    questions = relationship("QuestionRecord", back_populates="topic", cascade="all, delete-orphan")


class QuestionRecord(Base):
    __tablename__ = "question_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    topic_id = Column(String(36), ForeignKey("topic_records.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    expected_time_to_ans = Column(Integer, default=45, nullable=False)
    expected_answer_keywords_json = Column(Text, default="[]", nullable=False)
    order = Column(Integer, default=1, nullable=False)

    topic = relationship("TopicRecord", back_populates="questions")
    followups = relationship("FollowupRecord", back_populates="question", cascade="all, delete-orphan")


class FollowupRecord(Base):
    __tablename__ = "followup_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    question_id = Column(String(36), ForeignKey("question_records.id"), nullable=False)
    followup_text = Column(Text, nullable=False)
    expected_time_to_ans = Column(Integer, default=30, nullable=False)
    expected_answer_keywords_json = Column(Text, default="[]", nullable=False)
    order = Column(Integer, default=1, nullable=False)

    question = relationship("QuestionRecord", back_populates="followups")


class QuestionAssignment(Base):
    __tablename__ = "question_assignments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    bank_id = Column(String(36), ForeignKey("question_banks.id"), nullable=False)
    student_id = Column(String(36), ForeignKey("student_profiles.id"), nullable=True)  # Null = Global
    is_excluded = Column(Boolean, default=False, nullable=False)
    assigned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    question_bank = relationship("QuestionBank", back_populates="assignments")
    student = relationship("StudentProfile", back_populates="assignments")


class InterviewSessionRecord(Base):
    __tablename__ = "interview_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    student_id = Column(String(36), ForeignKey("student_profiles.id"), nullable=False)
    bank_id = Column(String(36), ForeignKey("question_banks.id"), nullable=False)
    room_name = Column(String(100), nullable=False, index=True)
    status = Column(String(50), default="created", nullable=False)  # created, in_progress, completed, discarded
    overall_score = Column(Float, nullable=True)
    ukvi_recommendation = Column(String(50), nullable=True)  # Genuine, Inconclusive, Not Genuine
    report_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    concluded_at = Column(DateTime, nullable=True)

    student = relationship("StudentProfile", back_populates="sessions")
    question_bank = relationship("QuestionBank")
    turn_evaluations = relationship("TurnEvaluationRecord", back_populates="session", cascade="all, delete-orphan")


class TurnEvaluationRecord(Base):
    __tablename__ = "turn_evaluations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("interview_sessions.id"), nullable=False)
    turn_type = Column(String(50), nullable=False)  # question, followup, reask
    reference_id = Column(String(36), nullable=False)
    spoken_prompt = Column(Text, nullable=False)
    candidate_transcript = Column(Text, default="", nullable=False)
    score = Column(Float, default=0.0, nullable=False)
    rubric_hits_json = Column(Text, default="[]", nullable=False)
    missed_keywords_json = Column(Text, default="[]", nullable=False)
    latency_ms = Column(Integer, default=0, nullable=False)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("InterviewSessionRecord", back_populates="turn_evaluations")
