from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


# ==============================================================================
# 🎓 1. STUDENT DATA MODEL (Compressed & Standardized)
# ==============================================================================

class StudentData(BaseModel):
    """Clean, compressed candidate data model for credibility & admissions evaluation."""
    student_id: str = Field(..., min_length=1, description="Unique Student/CAS reference ID")
    full_name: str = Field(..., min_length=1, description="Candidate legal full name")
    target_country: str = Field(default="United Kingdom", description="Target destination country")
    target_university: str = Field(..., min_length=1, description="Target UK university")
    target_course: str = Field(..., min_length=1, description="Target degree program")
    academic_background: str = Field(default="", description="Previous degree, major, CGPA and institution")
    english_proficiency: str = Field(default="", description="Test type and band score (e.g. IELTS 7.5)")
    tuition_fee_gbp: float = Field(default=0.0, description="Annual tuition fee in GBP")
    living_cost_gbp: float = Field(default=0.0, description="UKVI 9-month maintenance requirement in GBP")
    available_funds_gbp: float = Field(default=0.0, description="Total verified bank funds in GBP")
    sponsor_details: str = Field(default="", description="Funding source and UKVI 28-day rule compliance")
    post_study_plan: str = Field(default="", description="Post-graduation career plan and home country ties")


# ==============================================================================
# 🏛️ 2. UNIVERSITY DATA MODEL (Compressed & Standardized)
# ==============================================================================

class UniversityData(BaseModel):
    """Clean, compressed institution specifications for credibility evaluation."""
    university_id: str = Field(..., min_length=1, description="Unique institution identifier")
    official_name: str = Field(..., min_length=1, description="Official university name")
    campus_location: str = Field(default="", description="Campus and region")
    tuition_fee_gbp: float = Field(default=0.0, description="Standard international tuition fee amount")
    living_cost_guideline_gbp: float = Field(default=0.0, description="Official UKVI maintenance guideline amount")
    target_course: str = Field(default="", description="Degree program name")
    degree_level: str = Field(default="Postgraduate", description="Degree level (e.g. Postgraduate, Level 7)")
    duration_months: int = Field(default=12, description="Course length in months")
    core_modules: List[Dict[str, Any]] = Field(default_factory=list, description="List of core modules with codes/titles")
    campus_facilities: List[str] = Field(default_factory=list, description="Key labs, computing clusters, and facilities")
    competitor_differentiators: List[str] = Field(default_factory=list, description="Key differentiators vs competitors")
    compliance_rubrics: List[str] = Field(default_factory=list, description="Core UKVI compliance evaluation rubrics")


# =======================================================================# ==============================================================================
# 📋 3. NESTED QUESTION GENERATION STATE & MODELS (Tree Architecture: Pattern A)
# ==============================================================================

class FollowupItem(BaseModel):
    """Probing follow-up question nested under a primary question."""
    model_config = {"extra": "allow"}
    followup_order: int = Field(default=1, description="Sequence order of follow-up")
    followup: str = Field(description="The follow-up probe question text")
    expected_time_to_ans: int = Field(default=30, description="Expected time to answer in seconds")
    expected_answer_keywords: List[str] = Field(default_factory=list, description="Expected keywords / concepts")


class QuestionItem(BaseModel):
    """Primary standalone question containing its nested follow-ups."""
    model_config = {"extra": "allow"}
    question: str = Field(description="The primary standalone interview question text")
    difficulty: str = Field(default="Medium", description="Question difficulty")
    expected_time_to_ans: int = Field(default=45, description="Expected time to answer in seconds")
    expected_answer_keywords: List[str] = Field(default_factory=list, description="Expected keywords / concepts")
    followups: List[FollowupItem] = Field(
        default_factory=list,
        description="Probing follow-up questions linked directly to this primary question",
    )


class TopicItem(BaseModel):
    """Interview topic containing its primary standalone questions."""
    model_config = {"extra": "allow"}
    id: int = Field(description="Unique topic ID or sequence number")
    name: str = Field(description="Topic title")
    expected_time_to_ans: int = Field(default=60, description="Expected time for topic in seconds")
    questions: List[QuestionItem] = Field(
        default_factory=list,
        description="Primary questions under this topic (typically 1 standalone question)",
    )


class QuestionPlanModel(BaseModel):
    """Structured output format generated by OpenRouter thinking model."""
    topics: List[TopicItem] = Field(description="List of interview topics with nested questions and follow-ups")
    expected_total_time_to_ans: int = Field(default=45, description="Total expected interview time in minutes")
    difficulty: str = Field(default="Medium", description="Calibrated difficulty level")


# Backward compatibility aliases
TopicState = TopicItem
QuestionState = QuestionItem
SuggestedFollowupState = FollowupItem
QuestionListModelState = QuestionPlanModel



# ==============================================================================
# 🎯 4. PER-TURN ANSWER ACCURACY EVALUATION MODELS
# ==============================================================================

class AnswerAccuracyEvaluation(BaseModel):
    """Structured per-turn evaluation output produced by OpenRouter."""
    accuracy_score: float = Field(description="Accuracy score between 0.0 and 100.0")
    is_passed: bool = Field(description="True if accuracy_score >= 70.0, False otherwise")
    matched_keywords: List[str] = Field(default_factory=list, description="Keywords covered in candidate response")
    unmatched_keywords: List[str] = Field(default_factory=list, description="Keywords missed or lacking depth")
    feedback: str = Field(default="", description="Concise objective assessment")


class EvaluationRecord(BaseModel):
    """Persistent turn evaluation record stored in session history."""
    topic_id: int
    question_id: int = 0
    followup_order: Optional[int] = None
    turn_type: Literal["question", "suggested_followup"]
    attempt_number: int = 1
    accuracy_score: float
    is_passed: bool
    matched_keywords: List[str] = Field(default_factory=list)
    unmatched_keywords: List[str] = Field(default_factory=list)
    feedback: str = ""


# ==============================================================================
# 📊 5. FINAL EVALUATION REPORT MODELS
# ==============================================================================

class TopicEvaluationSummary(BaseModel):
    topic_id: int
    topic_name: str
    average_score: float
    is_passed: bool
    summary_feedback: str


class FinalEvaluation(BaseModel):
    """Comprehensive post-interview evaluation report synthesized from full transcript."""
    overall_score: float = Field(description="Overall interview score from 0.0 to 100.0")
    overall_status: Literal["PASSED", "CONDITIONAL_PASS", "FAILED"] = Field(
        description="PASSED (>=70%), CONDITIONAL_PASS (60-69%), FAILED (<60%)"
    )
    topic_breakdown: List[TopicEvaluationSummary] = Field(description="Score and summary for each topic")
    strengths: List[str] = Field(description="Key strengths demonstrated by candidate")
    areas_for_improvement: List[str] = Field(description="Gaps, missed technical concepts, or UKVI concerns")
    recommendation: str = Field(description="Official UKVI credibility & academic admissions recommendation")


# ==============================================================================
# 🧠 6. MAIN INTERVIEW STATE (LangGraph State Machine - Nested Tree Architecture)
# ==============================================================================

class InterviewState(TypedDict, total=False):
    """Multi-turn interview state machine operating on nested tree hierarchy."""
    # Data models (Strict Pydantic)
    student_id: Optional[str]
    university_id: Optional[str]
    student_data: Optional[StudentData]
    university_data: Optional[UniversityData]

    # Generated interview plan (Nested Tree: Topic -> Questions -> Followups)
    topics: List[TopicItem]
    expected_total_time_to_ans: int
    difficulty: str

    # Hierarchical State Cursors
    current_topic_idx: int       # 0..len(topics)-1
    current_question_idx: int    # 0..len(questions)-1 (typically 0)
    current_followup_idx: int    # -1 = Primary Question; 0..len(followups)-1 = Follow-up #N
    interview_status: Literal["not_started", "in_progress", "completed"]

    # Conversation history & turn evaluations
    messages: Annotated[List[BaseMessage], add_messages]
    evaluations: List[EvaluationRecord]

    # Final post-interview report
    final_evaluation: Optional[FinalEvaluation]