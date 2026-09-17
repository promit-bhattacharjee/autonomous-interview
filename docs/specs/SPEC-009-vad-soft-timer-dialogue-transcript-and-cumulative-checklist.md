# SPEC-009: VAD & Semantic Turn Detection, Blind Viva Dialogue Transcript, and Relational Unique Keyword Ledger Scoring

| Metadata | Details |
|---|---|
| **Spec ID** | `SPEC-009` |
| **Title** | VAD & Semantic Turn Detection, Blind Viva Dialogue Transcript, and Relational Unique Keyword Ledger Scoring |
| **Status** | `APPROVED` |
| **Version** | `1.1.0` |
| **Author** | Antigravity AI & Promit Bhattacharjee |
| **Created Date** | 2026-09-16 |
| **Governing Documents** | [constitution.md v2.2.0](file:///c:/Users/promi/OneDrive/Desktop/interviewv2/docs/constitution.md), [product_requirement.md](file:///c:/Users/promi/OneDrive/Desktop/interviewv2/product_requirement.md), [SPEC-008](file:///c:/Users/promi/OneDrive/Desktop/interviewv2/docs/specs/SPEC-008-static-instruction-and-turn-gated-interview-flow.md) |
| **Target Components** | `services/langgraph_agent/src/agent/state.py`, `services/langgraph_agent/src/agent/graphs/interview_exec.py`, `services/langgraph_agent/src/agent/worker.py`, `services/web_api/src/api/templates/student/interview.html` |

---

## 1. Context & Architectural Requirements

Following candidate testing and feedback on SPEC-008, four critical operational requirements have been defined:

1. **Soft-Threshold Timer with Dual VAD & Semantic Turn Detection:**
   - **No Hard Cutoffs:** When the countdown timer reaches `0s`, the system MUST NOT cut the candidate off mid-sentence.
   - **Acoustic VAD:** Monitors real-time microphone audio energy (RMS) to detect active speech vs. silence.
   - **Semantic Turn Detection:** Analyzes candidate transcript tokens:
     - **Continuation Markers:** Trailing conjunctions/fillers (`because`, `and`, `so`, `but`, `also`, `for example`, `such as`, `um`) signal incomplete thoughts and extend the silence threshold (up to 4.0s).
     - **Completion Markers:** Terminal punctuation (`.`, `!`, `?`) and concluding expressions (`that is all`, `that's my answer`, `thank you`) signal finished thoughts, triggering clean submission after a natural pause (1.2s - 1.5s).
     - **Soft Timer State:** If time reaches 0s while the candidate is still speaking, the UI indicates `Timer: Overtime (Wrapping up...)` without interrupting.

2. **Exam Integrity Guard (Blind Viva Dialogue Transcript):**
   - **Zero Live Rubric Leakage:** Candidate screens MUST NOT display matched keywords, missed keywords, pass/fail status, or percentage scores during the viva. Exposing missed keywords gives away the answers for re-ask probes.
   - **Live Dialogue Transcript:** The right panel displays a clean, alternating viva dialogue:
     - **🇬🇧 UKVI Examiner Bubble:** Spoken Question / Probe text, Topic Tag, Turn Number.
     - **🎙️ Candidate Bubble:** Spoken transcript recognized by speech engine.
   - **Post-Viva Isolation:** Complete scorecards, rubric matrices, and UKVI recommendations are strictly reserved for the final report and administrative dashboard.

3. **Retained Manual Override & Mic Gating:**
   - The candidate can click **"✅ Finished Speaking / Submit Turn"** at any time.
   - The microphone remains strictly hard-muted while the examiner speaks to guarantee zero acoustic feedback.

4. **Relational Deduplicated Keyword Ledger (Set / Hash Collection):**
   - Each question/follow-up maintains a **Unique Keyword Match Ledger** (Set / Hash Collection):
     - Every detected keyword is automatically added to a deduplicated set: `matched_set.add(keyword)`.
     - Duplicate mentions of keyword $A$ in Turn 1 and Turn 2 automatically collapse into a single unique entry.
     - Attempt 1 covers subset $H_1 \subseteq K$.
     - Re-ask probe targets the remaining uneliminated set: $K \setminus H_1$.
     - Attempt 2 covers subset $H_2 \subseteq K$.
     - Total cumulative hits across attempts: $H_{\text{total}} = H_1 \cup H_2$.
     - Cumulative score: $\frac{|H_1 \cup H_2|}{|K|} \times 100\%$.
     - The ledger is reset only when advancing to a new question, follow-up, or topic.

---

## 2. Implementation Specifications

### 2.1. LangGraph State & Execution (`interview_exec.py`, `state.py`)
- `InterviewExecutionState` maintains:
  - `active_question_id: str`
  - `active_question_hits: list[str]` (representing the unique set of matched keywords for the current question)
  - `total_question_keywords: list[str]`
- In `evaluate_answer_node`:
  - Uses `set` operations to append new matches to `active_question_hits`.
  - Recomputes the cumulative question score.
- In `ask_question_node`:
  - When triggering a re-ask, computes `unmatched = [k for k in total_kws if k not in active_question_hits]` and probes specifically on those unaddressed concepts.
- In `process_answer_node`:
  - Resets `active_question_hits = []` when advancing to the next question.

### 2.2. Student Frontend (`interview.html`)
- **Semantic Turn Detector & VAD Engine:**
  - `detectSemanticTurn(transcript, rmsVolume, timeRemaining)`:
    - Analyzes transcript trailing tokens for continuation vs completion.
    - Manages soft timer overtime and silence timers.
- **Transcript Dialogue Stream:**
  - Replaces `#scorecardBody` with `#dialogueTranscriptBody` containing alternating Examiner and Candidate message bubbles.
