from typing import Annotated, List, Literal, Optional, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field



class InitialExtracedTextState(TypedDict):
    extraced_text:str
    iterations:int
    conofidance:float
    difficulty:str
    expected_time_to_ans:int
    expected_words_to_ans:int

    
class InitialExtracedTextOutputState(BaseModel):
    extraced_text: str = Field(description="The cleaned and structured interview text.")
    iterations: int = Field(description="The number of iteration attempts (e.g., 1).")
    conofidance: float = Field(description="A confidence score of the extraction between 0.0 and 1.0.")
    difficulty: str = Field(description="The difficulty level of the interview")
    expected_time_to_ans:int = Field(description="The expected time to answer")
    expected_answer_keywords:List[str] = Field(description="The expected keywords should present in answer")

# Pydantic models for structured output
class TopicState(BaseModel):
    id: int
    name: str
    topic_order: int
    expected_time_to_ans:int
    expected_answer_keywords:list[str]


class QuestionState(BaseModel):
    topic_id: int
    question_id: int
    question_order: int
    question: str
    difficulty: str
    expected_time_to_ans:int
    expected_answer_keywords:list[str]


class SuggestedFollowupState(BaseModel):
    topic_id: int
    question_id: int
    followup_order: int
    followup: str
    expected_time_to_ans:int
    expected_answer_keywords:list[str]


class QuestionListModelState(BaseModel):
    topics: List[TopicState] = Field(description="List of interview topics")
    questions: List[QuestionState] = Field(description="List of interview questions")
    suggested_followups: List[SuggestedFollowupState] = Field(description="List of suggested follow-ups")
    expected_total_words_to_ans:int = Field(description="The total number of words to answer")
    expected_total_time_to_ans:int = Field(description="The total time to answer")
    difficulty: str = Field(description="The difficulty level of the interview")


class AnswerAccuracyEvaluation(BaseModel):
    accuracy_score: float = Field(description="Accuracy score between 0.0 and 100.0 based on keyword and conceptual coverage")
    is_passed: bool = Field(description="True if accuracy_score >= 70.0, False otherwise")
    matched_keywords: List[str] = Field(default_factory=list, description="Keywords from expected_answer_keywords covered in candidate answer")
    unmatched_keywords: List[str] = Field(default_factory=list, description="Keywords from expected_answer_keywords that were unmatched or missed in candidate answer")
    feedback: str = Field(description="Brief assessment of candidate response against expected keywords")


class EvaluationRecord(BaseModel):
    # Relational foreign keys
    topic_id: int = Field(description="Foreign key pointing to TopicState.id")
    question_id: int = Field(description="Foreign key pointing to QuestionState.question_id")
    followup_order: Optional[int] = Field(default=None, description="followup_order if suggested_followup, or None if main question")
    turn_type: Literal["question", "suggested_followup"] = Field(description="'question' for main questions, 'suggested_followup' for follow-up questions")
    attempt_number: int = Field(default=1, description="1 for initial attempt, 2 for re-ask attempt")

    # Evaluation metrics
    accuracy_score: float = Field(description="Accuracy score between 0.0 and 100.0")
    is_passed: bool = Field(description="True if accuracy_score >= 70.0, False otherwise")
    matched_keywords: List[str] = Field(default_factory=list, description="Keywords covered in candidate answer")
    unmatched_keywords: List[str] = Field(default_factory=list, description="Keywords that were unmatched or missed")
    feedback: str = Field(default="", description="Brief constructive evaluation")


# LangGraph state
class InterviewState(TypedDict, total=False):
    # Initial setup & candidate data
    extraced_text: str
    iterations: int
    conofidance: float
    expected_time_to_ans: int
    expected_words_to_ans: int
    expected_answer_keywords: List[str]

    # Generated interview plan
    messages: Annotated[List[BaseMessage], add_messages]
    topics: List[TopicState]
    questions: List[QuestionState]
    suggested_followups: List[SuggestedFollowupState]
    expected_total_time_to_ans: int
    difficulty: str
    expected_total_words_to_ans: int

    # Turn-by-turn tracking & routing
    topic_id: int
    current_topic_id: int
    current_question_index: int
    is_followup: bool
    is_reask: bool
    interview_status: str

    # Relational evaluation history
    evaluations: List[EvaluationRecord]