from typing import List
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from interview.helper import (
    ensure_text_content,
    get_speech_llm,
    get_structured_thinking_llm,
)
from interview.prompts import (
    ANSWER_EVALUATION_HUMAN_PROMPT,
    ANSWER_EVALUATION_SYSTEM_PROMPT,
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
    QuestionPlanModel,
)
from interview.tools.question_helpers import (
    advance_turn,
    get_current_turn_target,
    get_latest_evaluation,
    is_current_turn_reask,
)

# ==============================================================================
# NODE 1: Dynamic Question Generation Node (Nested Tree Architecture: Pattern A)
# ==============================================================================

def generate_questions_node(state: InterviewState) -> dict:
    """
    Generates structured interview topics with nested standalone questions and follow-ups
    using OpenRouter DeepSeek V4 Flash 0731. Operates on pre-validated state.
    """
    expected_time = state.get("expected_total_time_to_ans", 45)
    student_data = state.get("student_data")
    university_data = state.get("university_data")

    target_univ = student_data.target_university if student_data else ""
    target_course = student_data.target_course if student_data else ""
    tuition_fee = student_data.tuition_fee_gbp if student_data else 0.0
    living_cost = student_data.living_cost_gbp if student_data else 0.0

    expected_kw = [
        str(target_univ),
        str(target_course),
        f"tuition {tuition_fee}",
        f"maintenance {living_cost}",
        "28-day rule",
        "home country return",
    ]
    if university_data and university_data.core_modules:
        for mod in university_data.core_modules[:2]:
            mod_title = mod.get("title") or mod.get("module_name") if isinstance(mod, dict) else getattr(mod, "title", getattr(mod, "module_name", None))
            if mod_title:
                expected_kw.append(mod_title)

    system_content = QUESTION_GENERATION_FROM_STATE_PROMPT.format(
        student_info=student_data.model_dump_json(indent=2) if student_data else "{}",
        university_info=university_data.model_dump_json(indent=2) if university_data else "{}",
    )

    human_content = QUESTION_GENERATION_HUMAN_PROMPT.format(
        difficulty=state.get("difficulty", "Medium"),
        expected_time_to_ans=expected_time,
        expected_answer_keywords=", ".join([k for k in expected_kw if k]),
    )

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=human_content),
    ]

    structured_llm = get_structured_thinking_llm(QuestionPlanModel, temperature=0.0)
    result: QuestionPlanModel = structured_llm.invoke(messages)

    return {
        "student_data": student_data,
        "university_data": university_data,
        "topics": result.topics,
        "expected_total_time_to_ans": result.expected_total_time_to_ans,
        "difficulty": result.difficulty,
        "current_topic_idx": 0,
        "current_question_idx": 0,
        "current_followup_idx": -1,
        "interview_status": "in_progress",
        "evaluations": [],
    }


# ==============================================================================
# NODE 2: Per-Turn Answer Evaluation Node (Powered by OpenRouter DeepSeek V4 Flash 0731)
# ==============================================================================

def evaluate_answer_node(state: InterviewState) -> dict:
    """
    Evaluates candidate's latest response against active relational question and keywords
    using OpenRouter DeepSeek V4 Flash 0731. Appends an EvaluationRecord.
    """
    messages_list = state.get("messages", [])
    last_ai_msg = next((m for m in reversed(messages_list) if isinstance(m, AIMessage)), None)
    last_human_msg = next((m for m in reversed(messages_list) if isinstance(m, HumanMessage)), None)

    if not last_human_msg:
        return {}

    question_text, keywords_list, topic_name, is_followup = get_current_turn_target(state)
    if not question_text:
        return {}

    context_type = "Follow-up Question" if is_followup else "Primary Standalone Question"

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

    # OpenRouter thinking model evaluates accuracy (DeepSeek V4 Flash 0731 with fallback)
    structured_llm = get_structured_thinking_llm(AnswerAccuracyEvaluation, temperature=0.0)
    result: AnswerAccuracyEvaluation = structured_llm.invoke(eval_messages)

    t_idx = state.get("current_topic_idx", 0)
    q_idx = state.get("current_question_idx", 0)
    f_idx = state.get("current_followup_idx", -1)
    turn_type = "suggested_followup" if is_followup else "question"

    prior_evals = [
        e for e in state.get("evaluations", [])
        if e.topic_id == t_idx
        and e.question_id == q_idx
        and e.followup_order == (f_idx if is_followup else None)
    ]
    attempt_number = len(prior_evals) + 1

    record = EvaluationRecord(
        topic_id=t_idx,
        question_id=q_idx,
        followup_order=f_idx if is_followup else None,
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
    is_completed = state.get("interview_status") == "completed"
    question_to_ask, _, topic_name, is_followup = get_current_turn_target(state)
    if not question_to_ask:
        is_completed = True

    # Speech LLM for phrasing questions
    speech_llm = get_speech_llm()

    if is_completed:
        conclude_msg = speech_llm.invoke([
            SystemMessage(content=INTERVIEW_CONCLUDE_PROMPT),
            HumanMessage(content="All questions have been completed. Please deliver concluding remarks to the candidate."),
        ])
        return {
            "interview_status": "completed",
            "messages": [ensure_text_content(conclude_msg)],
        }

    is_reask = is_current_turn_reask(state)
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
        "messages": [ensure_text_content(ai_response)],
        "interview_status": "in_progress",
    }


# ==============================================================================
# NODE 4: Candidate Answer Process & Sequencing Node (Nested Tree Architecture)
# ==============================================================================

def process_answer_node(state: InterviewState) -> dict:
    """
    Nested tree cursor sequencer:
    - If answer failed (< 70%) on attempt 1, keeps cursors for re-ask.
    - If passed (>= 70%) or retry completed, advances cursor (follow-up -> question -> topic).
    """
    if state.get("interview_status") == "completed":
        return {"interview_status": "completed"}

    return advance_turn(state)


# ==============================================================================
# NODE 5: Post-Interview Final Evaluation Node (Powered by OpenRouter DeepSeek V4 Flash 0731)
# ==============================================================================

def generate_final_evaluation_node(state: InterviewState) -> dict:
    """
    Synthesizes the full verbatim interview transcript and per-turn evaluation metrics
    into a comprehensive final UKVI credibility and academic admissions report using OpenRouter DeepSeek V4 Flash 0731.
    """
    messages = state.get("messages", [])
    evaluations = state.get("evaluations", [])
    student_data = state.get("student_data") or {}
    university_data = state.get("university_data") or {}

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
        student_info=student_data.model_dump_json(indent=2) if student_data else "{}",
        university_info=university_data.model_dump_json(indent=2) if university_data else "{}",
        turn_evaluations=eval_summary,
        transcript=full_transcript,
    )

    eval_messages = [
        SystemMessage(content=FINAL_EVALUATION_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]

    # OpenRouter thinking model generates final report (DeepSeek V4 Flash 0731 with fallback)
    structured_llm = get_structured_thinking_llm(FinalEvaluation, temperature=0.0)
    final_report: FinalEvaluation = structured_llm.invoke(eval_messages)

    return {
        "final_evaluation": final_report,
        "interview_status": "completed",
    }
