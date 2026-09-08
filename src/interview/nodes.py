import json
from typing import Any, List
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from interview.llm import get_speech_llm, get_thinking_llm
from interview.prompts import (
    ANSWER_EVALUATION_HUMAN_PROMPT,
    ANSWER_EVALUATION_SYSTEM_PROMPT,
    DOCUMENT_EXTRACTION_PROMPT,
    FINAL_EVALUATION_HUMAN_PROMPT,
    FINAL_EVALUATION_SYSTEM_PROMPT,
    INTERVIEW_CONCLUDE_PROMPT,
    INTERVIEW_QUESTION_PROMPT,
    QUESTION_GENERATION_FROM_STATE_PROMPT,
    QUESTION_GENERATION_HUMAN_PROMPT,
)
from interview.state import (
    AnswerAccuracyEvaluation,
    EvaluationRecord,
    FinalEvaluation,
    InterviewState,
    QuestionListModelState,
    StudentData,
    UniversityData,
)
from interview.tools.question_helpers import (
    get_active_followup,
    get_active_question,
    get_active_topic,
    get_active_turn_target,
    get_evaluations_for_turn,
    get_latest_evaluation,
    get_next_relational_turn,
    is_active_turn_followup,
    is_active_turn_reask,
)


def _serialize_model(obj: Any) -> Any:
    """Helper to convert Pydantic models or dicts into JSON-friendly dicts."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return {k: _serialize_model(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_serialize_model(v) for v in obj]
    return obj


def _ensure_text_content(msg: AIMessage) -> AIMessage:
    """Normalizes multimodal content blocks into clean string text."""
    if isinstance(msg.content, list):
        text_parts = [
            p.get("text", "") if isinstance(p, dict) else str(p)
            for p in msg.content
        ]
        msg.content = "".join(text_parts).strip()
    return msg


def _get_structured_thinking_llm(schema: Any):
    """
    Returns a structured thinking model using OpenRouter DeepSeek V3,
    with automatic fallback to LLaMA-3.3-70B if upstream OpenRouter providers
    experience temporary rate-limiting.
    """
    primary = get_thinking_llm()
    fallback = get_thinking_llm(model_name="meta-llama/llama-3.3-70b-instruct")
    try:
        return primary.with_structured_output(schema).with_fallbacks([fallback.with_structured_output(schema)])
    except Exception:
        return primary.with_structured_output(schema)


# ==============================================================================
# NODE 1: Dynamic Question Generation Node (Powered by OpenRouter DeepSeek V3)
# ==============================================================================

def generate_questions_node(state: InterviewState) -> dict:
    """
    Generates structured interview topics, questions, and suggested follow-ups
    using OpenRouter DeepSeek V3. Uses compressed StudentData and UniversityData.
    """
    expected_time = state.get("expected_total_time_to_ans", 45)

    # 1. Resolve and validate compressed StudentData
    student_data = state.get("student_data")
    if not student_data:
        student_id = state.get("student_id")
        if not student_id:
            error_msg = "❌ [DATA VALIDATION FAILED]: Neither 'student_data' nor 'student_id' was provided. Interview session terminated."
            return {
                "interview_status": "completed",
                "messages": [AIMessage(content=error_msg)],
            }
        from mock_api import fetch_student_api
        raw_student = fetch_student_api(student_id)
        if not raw_student:
            error_msg = f"❌ [DATA VALIDATION FAILED]: Student profile for student_id '{student_id}' was not found in data repository. Interview session terminated."
            return {
                "interview_status": "completed",
                "messages": [AIMessage(content=error_msg)],
            }
        student_data = StudentData(**{k: v for k, v in raw_student.items() if k in StudentData.model_fields})

    # Validate essential student fields
    missing_student_fields = []
    if not getattr(student_data, "student_id", None):
        missing_student_fields.append("student_id")
    if not getattr(student_data, "full_name", None):
        missing_student_fields.append("full_name")
    if not getattr(student_data, "target_university", None):
        missing_student_fields.append("target_university")
    if not getattr(student_data, "target_course", None):
        missing_student_fields.append("target_course")

    if missing_student_fields:
        error_msg = f"❌ [DATA VALIDATION FAILED]: Incomplete student data. Missing required fields: {', '.join(missing_student_fields)}. Interview session terminated."
        return {
            "interview_status": "completed",
            "messages": [AIMessage(content=error_msg)],
        }

    # 2. Resolve and validate compressed UniversityData
    university_data = state.get("university_data")
    if not university_data:
        university_id = state.get("university_id")
        if not university_id:
            error_msg = "❌ [DATA VALIDATION FAILED]: Neither 'university_data' nor 'university_id' was provided. Interview session terminated."
            return {
                "interview_status": "completed",
                "messages": [AIMessage(content=error_msg)],
            }
        from mock_api import fetch_university_api
        raw_univ = fetch_university_api(university_id)
        if not raw_univ:
            error_msg = f"❌ [DATA VALIDATION FAILED]: University specifications for university_id '{university_id}' were not found in data repository. Interview session terminated."
            return {
                "interview_status": "completed",
                "messages": [AIMessage(content=error_msg)],
            }
        university_data = UniversityData(**{k: v for k, v in raw_univ.items() if k in UniversityData.model_fields})

    # Validate essential university fields
    missing_univ_fields = []
    if not getattr(university_data, "university_id", None):
        missing_univ_fields.append("university_id")
    if not getattr(university_data, "official_name", None):
        missing_univ_fields.append("official_name")

    if missing_univ_fields:
        error_msg = f"❌ [DATA VALIDATION FAILED]: Incomplete university data. Missing required fields: {', '.join(missing_univ_fields)}. Interview session terminated."
        return {
            "interview_status": "completed",
            "messages": [AIMessage(content=error_msg)],
        }

    expected_kw = [
        student_data.target_university,
        student_data.target_course,
        f"tuition {student_data.tuition_fee_gbp}",
        f"maintenance {student_data.living_cost_gbp}",
        "28-day rule",
        "home country return",
    ]
    if university_data.core_modules:
        for mod in university_data.core_modules[:2]:
            mod_title = mod.get("title") or mod.get("module_name")
            if mod_title:
                expected_kw.append(mod_title)

    student_json = json.dumps(_serialize_model(student_data), indent=2)
    university_json = json.dumps(_serialize_model(university_data), indent=2)

    human_content = QUESTION_GENERATION_HUMAN_PROMPT.format(
        student_info=student_json,
        university_info=university_json,
        extraced_text="Standardized admissions & credibility specifications.",
        difficulty=state.get("difficulty", "Medium"),
        expected_time_to_ans=expected_time,
        expected_answer_keywords=", ".join(expected_kw),
    )

    messages = [
        SystemMessage(content=QUESTION_GENERATION_FROM_STATE_PROMPT),
        HumanMessage(content=human_content),
    ]

    # Use OpenRouter thinking model (DeepSeek V3 with fallback)
    structured_llm = _get_structured_thinking_llm(QuestionListModelState)
    result: QuestionListModelState = structured_llm.invoke(messages)

    first_topic_id = result.topics[0].id if result.topics else None
    first_question_id = result.questions[0].question_id if result.questions else None

    return {
        "student_data": student_data,
        "university_data": university_data,
        "topics": result.topics,
        "questions": result.questions,
        "suggested_followups": result.suggested_followups,
        "expected_total_time_to_ans": result.expected_total_time_to_ans,
        "difficulty": result.difficulty,
        "active_topic_id": first_topic_id,
        "active_question_id": first_question_id,
        "active_followup_order": None,
        "interview_status": "in_progress",
        "evaluations": [],
    }


# ==============================================================================
# NODE 2: Per-Turn Answer Evaluation Node (Powered by OpenRouter DeepSeek V3)
# ==============================================================================

def evaluate_answer_node(state: InterviewState) -> dict:
    """
    Evaluates candidate's latest response against active relational question and keywords
    using OpenRouter DeepSeek V3. Appends an EvaluationRecord.
    """
    messages_list = state.get("messages", [])
    last_ai_msg = next((m for m in reversed(messages_list) if isinstance(m, AIMessage)), None)
    last_human_msg = next((m for m in reversed(messages_list) if isinstance(m, HumanMessage)), None)

    active_q = get_active_question(state)
    if not last_human_msg or not active_q:
        return {}

    active_topic = get_active_topic(state)
    topic_name = active_topic.name if active_topic else "UKVI Credibility & Academic Fit"

    question_text, keywords_list, context_type = get_active_turn_target(state)

    prompt_content = ANSWER_EVALUATION_HUMAN_PROMPT.format(
        topic_name=topic_name,
        context_type=context_type,
        last_ai_message=last_ai_msg.content if last_ai_msg else "N/A",
        last_human_message=last_human_msg.content if last_human_msg else "",
        expected_keywords=", ".join(keywords_list) if keywords_list else "General technical accuracy and relevant concepts",
    )

    eval_messages = [
        SystemMessage(content=ANSWER_EVALUATION_SYSTEM_PROMPT),
        HumanMessage(content=prompt_content),
    ]

    # OpenRouter thinking model evaluates accuracy (DeepSeek V3 with fallback)
    structured_llm = _get_structured_thinking_llm(AnswerAccuracyEvaluation)
    result: AnswerAccuracyEvaluation = structured_llm.invoke(eval_messages)

    is_followup = is_active_turn_followup(state)
    followup_order = state.get("active_followup_order")
    turn_type = "suggested_followup" if is_followup else "question"

    prior_evals = get_evaluations_for_turn(
        state, active_q.question_id, turn_type, followup_order=followup_order
    )
    attempt_number = len(prior_evals) + 1

    record = EvaluationRecord(
        topic_id=active_q.topic_id,
        question_id=active_q.question_id,
        followup_order=followup_order,
        turn_type=turn_type,
        attempt_number=attempt_number,
        accuracy_score=float(result.accuracy_score),
        is_passed=bool(result.is_passed),
        matched_keywords=result.matched_keywords,
        unmatched_keywords=result.unmatched_keywords,
        feedback=result.feedback,
    )

    current_evaluations = list(state.get("evaluations", []))
    current_evaluations.append(record)

    return {
        "evaluations": current_evaluations,
    }


# ==============================================================================
# NODE 3: Interviewer Utterance Formulator Node (Gemini Conversational Phrasing)
# ==============================================================================

def ask_question_node(state: InterviewState) -> dict:
    """
    Formulates and delivers the conversational interview question, follow-up, or re-ask.
    Uses Gemini for conversational interviewer voice phrasing.
    """
    active_q = get_active_question(state)
    is_completed = state.get("interview_status") == "completed" or not active_q

    # Speech LLM for phrasing questions
    speech_llm = get_speech_llm()

    if is_completed:
        conclude_msg = speech_llm.invoke([
            SystemMessage(content=INTERVIEW_CONCLUDE_PROMPT),
            HumanMessage(content="All questions have been completed. Please deliver concluding remarks to the candidate."),
        ])
        return {
            "interview_status": "completed",
            "messages": [_ensure_text_content(conclude_msg)],
            "active_topic_id": None,
            "active_question_id": None,
            "active_followup_order": None,
        }

    active_topic = get_active_topic(state)
    topic_name = active_topic.name if active_topic else "UKVI Credibility"

    is_reask = is_active_turn_reask(state)
    is_followup = is_active_turn_followup(state)
    question_to_ask, _, _ = get_active_turn_target(state)

    latest_eval = get_latest_evaluation(state)
    unmatched_keywords = latest_eval.unmatched_keywords if (latest_eval and is_reask) else []

    prompt_content = INTERVIEW_QUESTION_PROMPT.format(
        topic_name=topic_name,
        question_text=question_to_ask,
        is_followup="Yes" if is_followup else "No",
        is_reask="Yes" if is_reask else "No",
        unmatched_keywords=", ".join(unmatched_keywords) if unmatched_keywords else "None",
    )

    history = state.get("messages", [])[-2:] if state.get("messages") else []
    if is_reask:
        instruction = (
            "The candidate's previous answer missed some required details or scored below threshold. "
            "Politely acknowledge their answer and re-ask or prompt them to elaborate."
        )
    elif is_followup:
        instruction = "Please ask the candidate this follow-up question naturally."
    else:
        instruction = "Please introduce and present this interview question to the candidate."

    messages = [SystemMessage(content=prompt_content)] + list(history) + [HumanMessage(content=instruction)]
    ai_response = speech_llm.invoke(messages)

    return {
        "messages": [_ensure_text_content(ai_response)],
        "active_topic_id": active_q.topic_id,
        "active_question_id": active_q.question_id,
        "interview_status": "in_progress",
    }


# ==============================================================================
# NODE 4: Candidate Answer Process & Sequencing Node
# ==============================================================================

def process_answer_node(state: InterviewState) -> dict:
    """
    Relational turn sequencer:
    - If answer failed (< 70%) on attempt 1, keeps pointers for re-ask.
    - If passed (>= 70%) or retry completed, advances to next question/follow-up/topic.
    """
    active_q = get_active_question(state)
    if not active_q or state.get("interview_status") == "completed":
        return {"interview_status": "completed"}

    if is_active_turn_reask(state):
        return {}

    next_topic_id, next_question_id, next_followup_order, is_completed = get_next_relational_turn(state)

    if is_completed or next_question_id is None:
        return {
            "interview_status": "completed",
            "active_topic_id": None,
            "active_question_id": None,
            "active_followup_order": None,
        }

    return {
        "active_topic_id": next_topic_id,
        "active_question_id": next_question_id,
        "active_followup_order": next_followup_order,
    }


# ==============================================================================
# NODE 5: Post-Interview Final Evaluation Node (Powered by OpenRouter DeepSeek V3)
# ==============================================================================

def generate_final_evaluation_node(state: InterviewState) -> dict:
    """
    Synthesizes the full verbatim interview transcript and per-turn evaluation metrics
    into a comprehensive final UKVI credibility and academic admissions report using OpenRouter DeepSeek V3.
    """
    messages = state.get("messages", [])
    evaluations = state.get("evaluations", [])
    student_data = state.get("student_data") or StudentData()
    university_data = state.get("university_data") or UniversityData()

    # 1. Format Verbatim Transcript
    transcript_lines = []
    for msg in messages:
        sender = "Interviewer" if isinstance(msg, AIMessage) else "Candidate"
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        transcript_lines.append(f"[{sender}]: {content}")
    full_transcript = "\n\n".join(transcript_lines) if transcript_lines else "No conversation recorded."

    # 2. Format Turn Evaluations Summary
    eval_lines = []
    for idx, e in enumerate(evaluations, 1):
        status = "PASSED" if e.is_passed else "BELOW_THRESHOLD"
        matched = ", ".join(e.matched_keywords) if e.matched_keywords else "None"
        unmatched = ", ".join(e.unmatched_keywords) if e.unmatched_keywords else "None"
        eval_lines.append(
            f"Turn {idx} (Topic {e.topic_id}, Q{e.question_id}, Attempt {e.attempt_number}): "
            f"Score: {e.accuracy_score:.1f}% ({status}) | Matched: [{matched}] | Unmatched: [{unmatched}] | "
            f"Feedback: {e.feedback}"
        )
    eval_summary = "\n".join(eval_lines) if eval_lines else "No individual evaluations recorded."

    human_content = FINAL_EVALUATION_HUMAN_PROMPT.format(
        student_info=json.dumps(_serialize_model(student_data), indent=2),
        university_info=json.dumps(_serialize_model(university_data), indent=2),
        turn_evaluations=eval_summary,
        transcript=full_transcript,
    )

    eval_messages = [
        SystemMessage(content=FINAL_EVALUATION_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]

    # OpenRouter thinking model generates final report (DeepSeek V3 with fallback)
    structured_llm = _get_structured_thinking_llm(FinalEvaluation)
    final_report: FinalEvaluation = structured_llm.invoke(eval_messages)

    return {
        "final_evaluation": final_report,
        "interview_status": "completed",
    }
