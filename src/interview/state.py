from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


# ==============================================================================
# 🎓 1. STUDENT DATA MODEL (Compressed & Standardized)
# ==============================================================================

class StudentData(BaseModel):
    """Clean, compressed candidate data model for credibility & admissions evaluation."""
    student_id: str = Field(default="UK-CAS-2026-9041", description="Unique Student/CAS reference ID")
    full_name: str = Field(default="Tariqul Islam", description="Candidate legal full name")
    target_country: str = Field(default="United Kingdom", description="Target destination country")
    target_university: str = Field(default="University of Hertfordshire", description="Target UK university")
    target_course: str = Field(default="MSc Artificial Intelligence with Advanced Research", description="Target degree program")
    academic_background: str = Field(default="", description="Previous degree, major, CGPA and institution")
    english_proficiency: str = Field(default="", description="Test type and band score (e.g. IELTS 7.5)")
    tuition_fee_gbp: float = Field(default=16500.0, description="Annual tuition fee in GBP")
    living_cost_gbp: float = Field(default=12500.0, description="UKVI 9-month maintenance requirement in GBP")
    available_funds_gbp: float = Field(default=35000.0, description="Total verified bank funds in GBP")
    sponsor_details: str = Field(default="", description="Funding source and UKVI 28-day rule compliance")
    post_study_plan: str = Field(default="", description="Post-graduation career plan and home country ties")


# ==============================================================================
# 🏛️ 2. UNIVERSITY DATA MODEL (Compressed & Standardized)
# ==============================================================================

class UniversityData(BaseModel):
    """Clean, compressed institution specifications for credibility evaluation."""
    university_id: str = Field(default="UK-HERTS-01", description="Unique institution identifier")
    official_name: str = Field(default="University of Hertfordshire", description="Official university name")
    campus_location: str = Field(default="Hatfield, Hertfordshire (Outside London)", description="Campus and region")
    tuition_fee_gbp: float = Field(default=16500.0, description="Standard international tuition fee amount")
    living_cost_guideline_gbp: float = Field(default=12500.0, description="Official UKVI maintenance guideline amount")
    target_course: str = Field(default="", description="Degree program name")
    degree_level: str = Field(default="Postgraduate", description="Degree level (e.g. Postgraduate, Level 7)")
    duration_months: int = Field(default=24, description="Course length in months")
    core_modules: List[Dict[str, Any]] = Field(default_factory=list, description="List of core modules with codes/titles")
    campus_facilities: List[str] = Field(default_factory=list, description="Key labs, computing clusters, and facilities")
    competitor_differentiators: List[str] = Field(default_factory=list, description="Key differentiators vs competitors")
    compliance_rubrics: List[str] = Field(default_factory=list, description="Core UKVI compliance evaluation rubrics")


# ==============================================================================
# 📋 3. QUESTION GENERATION STATE & MODELS
# ==============================================================================

class TopicState(BaseModel):
    id: int = Field(description="Unique topic ID")
    name: str = Field(description="Topic title")
    topic_order: int = Field(description="Sequence order")
    expected_time_to_ans: int = Field(default=45, description="Expected time to answer in seconds")
    expected_answer_keywords: List[str] = Field(default_factory=list, description="Key concepts for this topic")


class QuestionState(BaseModel):
    topic_id: int = Field(description="Parent topic ID")
    question_id: int = Field(description="Unique question ID")
    question_order: int = Field(description="Order within topic")
    question: str = Field(description="The interview question text")
    difficulty: str = Field(default="Medium", description="Question difficulty")
    expected_time_to_ans: int = Field(default=45, description="Expected time to answer in seconds")
    expected_answer_keywords: List[str] = Field(default_factory=list, description="Expected keywords / concepts")


class SuggestedFollowupState(BaseModel):
    topic_id: int = Field(description="Parent topic ID")
    question_id: int = Field(description="Parent question ID")
    followup_order: int = Field(description="Sequence order of follow-up")
    followup: str = Field(description="The follow-up question text")
    expected_time_to_ans: int = Field(default=30, description="Expected time to answer in seconds")
    expected_answer_keywords: List[str] = Field(default_factory=list, description="Expected keywords / concepts")


class QuestionListModelState(BaseModel):
    """Structured output format generated by OpenRouter thinking model."""
    topics: List[TopicState] = Field(description="List of interview topics")
    questions: List[QuestionState] = Field(description="List of interview questions")
    suggested_followups: List[SuggestedFollowupState] = Field(default_factory=list, description="Suggested follow-up questions")
    expected_total_time_to_ans: int = Field(default=45, description="Total expected interview time")
    difficulty: str = Field(default="Medium", description="Calibrated difficulty level")


class QuestionGenerationState(TypedDict, total=False):
    """State slice specifically for question generation workflow."""
    student_data: Optional[StudentData]
    university_data: Optional[UniversityData]
    student_id: Optional[str]
    university_id: Optional[str]
    difficulty: str
    expected_time_to_ans: int
    expected_total_time_to_ans: int
    topics: List[TopicState]
    questions: List[QuestionState]
    suggested_followups: List[SuggestedFollowupState]


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
    question_id: int
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
# 🧠 6. MAIN INTERVIEW STATE (LangGraph State Machine)
# ==============================================================================

class InterviewState(TypedDict, total=False):
    """Multi-turn interview state machine."""
    # Data models
    student_id: Optional[str]
    university_id: Optional[str]
    student_data: Optional[StudentData]
    university_data: Optional[UniversityData]

    # Generated interview plan
    topics: List[TopicState]
    questions: List[QuestionState]
    suggested_followups: List[SuggestedFollowupState]
    expected_total_time_to_ans: int
    difficulty: str

    # Active Relational Pointers (Foreign Keys)
    active_topic_id: Optional[int]
    active_question_id: Optional[int]
    active_followup_order: Optional[int]
    interview_status: Literal["not_started", "in_progress", "completed"]

    # Conversation history & turn evaluations
    messages: Annotated[List[BaseMessage], add_messages]
    evaluations: List[EvaluationRecord]

    # Final post-interview report
    final_evaluation: Optional[FinalEvaluation]