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
    expected_words_to_ans:int = Field(description="The expected number of words to answer")

# Pydantic models for structured output
class TopicState(BaseModel):
    id: int
    name: str
    topic_order: int
    expected_time_to_ans:int
    expected_words_to_ans:int


class QuestionState(BaseModel):
    topic_id: int
    question_id: int
    question_order: int
    question: str
    difficulty: str
    expected_answer: str
    expected_time_to_ans:int
    expected_words_to_ans:int


class SuggestedFollowupState(BaseModel):
    topic_id: int
    question_id: int
    followup_order: int
    followup: str
    expected_time_to_ans:int
    expected_words_to_ans:int


class QuestionListModelState(BaseModel):
    topics: List[TopicState] = Field(description="List of interview topics")
    questions: List[QuestionState] = Field(description="List of interview questions")
    suggested_followups: List[SuggestedFollowupState] = Field(description="List of suggested follow-ups")
    expected_total_words_to_ans:int = Field(description="The total number of words to answer")
    expected_total_time_to_ans:int = Field(description="The total time to answer")
    difficulty: str = Field(description="The difficulty level of the interview")


# LangGraph state
class InterviewState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    topics: List[TopicState]
    questions: List[QuestionState]
    suggested_followups: List[SuggestedFollowupState]
    expected_total_time_to_ans: int
    difficulty: str
    expected_total_words_to_ans: int