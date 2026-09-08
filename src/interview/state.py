from typing import Annotated, List, Optional, TypedDict
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
    interview_status: str

    # Answer accuracy evaluation & retry tracking
    last_accuracy: float
    is_passed: bool
    matched_keywords: List[str]
    unmatched_keywords: List[str]
    retry_count: int
    is_reask: bool