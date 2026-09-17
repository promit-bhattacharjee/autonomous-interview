# SPEC-008: Static Instruction Audio & Turn-Gated Voice Interview Workflow

| Metadata | Details |
|---|---|
| **Spec ID** | `SPEC-008` |
| **Title** | Pre-Rendered Static Instruction Audio, Strict Turn-Based State Machine, and WebRTC Microphone Gating |
| **Status** | `APPROVED / IN-PROGRESS` |
| **Version** | `1.0.0` |
| **Author** | Antigravity AI & Promit Bhattacharjee |
| **Created Date** | 2026-09-16 |
| **Governing Documents** | [constitution.md v2.2.0](file:///c:/Users/promi/OneDrive/Desktop/interviewv2/docs/constitution.md), [product_requirement.md](file:///c:/Users/promi/OneDrive/Desktop/interviewv2/product_requirement.md), [SPEC-005](file:///c:/Users/promi/OneDrive/Desktop/interviewv2/docs/specs/SPEC-005-livekit-session-lifecycle-and-discard-guard.md) |
| **Target Components** | `services/web_api/src/api/static/audio/`, `services/web_api/src/api/templates/student/interview.html`, `services/langgraph_agent/src/agent/worker.py` |

---

## 1. Context & Motivation

In the UKVI Credibility & Academic Voice Interview system, candidates must experience a realistic, structured, and professional interview environment. A key requirement of an authentic viva or credibility examination is that the interaction is strictly **turn-based**:
1. **Instruction First:** Upon connecting, the candidate must first be briefed on the rules, structure, and expectations of the assessment via a standardized AI examiner voice message.
2. **Zero Recurring LLM/TTS Fees for Invariant Briefing:** The instruction message is static and unchanging across all candidates; it MUST NOT invoke real-time LLM token generation or recurring TTS synthesis on every session. Instead, it must be pre-rendered into a static audio asset (`/static/audio/interview_instructions.mp3`) and served directly with immutable HTTP caching.
3. **Strict Turn Gating & Microphone Isolation:** The candidate's microphone must be **hard-muted** (`setMicrophoneEnabled(false)`) and speech recognition deactivated during both the instruction briefing and while the examiner is delivering each question.
4. **Visual & Auditory Synchronization:** The question text from the question bank must appear on screen simultaneously with the spoken examiner audio so candidates can both read and hear the question.
5. **Candidate Answering Window:** Only when the examiner finishes speaking does the system transition the candidate into an active speaking turn—un-muting the microphone, activating speech recognition, and initiating the countdown timer.

---

## 2. Finite State Machine (FSM)

The interview client transitions through a strictly ordered finite state machine:

```mermaid
stateDiagram-v2
    [*] --> STATE_STANDBY: Load Interview Screen
    STATE_STANDBY --> STATE_CONNECTING: Click "Start Voice Interview"
    STATE_CONNECTING --> STATE_INSTRUCTION: WebRTC Connected
    
    state STATE_INSTRUCTION {
        [*] --> PlayStaticAudio: Stream /static/audio/interview_instructions.mp3
        PlayStaticAudio --> DisplayInstructionText: Show Guidelines & Rule Banner
        Note right of STATE_INSTRUCTION: Mic HARD-MUTED 🔇\nSTT OFF\nTimer OFF
    }
    
    STATE_INSTRUCTION --> STATE_QUESTION_PLAYING: Audio Ended or Candidate Skips
    
    state STATE_QUESTION_PLAYING {
        [*] --> RenderQuestionText: Populate #questionPrompt
        RenderQuestionText --> StreamExaminerTTS: Stream /api/tts British Neural Voice
        Note right of STATE_QUESTION_PLAYING: Mic HARD-MUTED 🔇\nSTT OFF\nFeedback Loop Blocked
    }
    
    STATE_QUESTION_PLAYING --> STATE_CANDIDATE_TURN: Examiner Audio Ended (audio.onended)
    
    state STATE_CANDIDATE_TURN {
        [*] --> UnmuteMicrophone: setMicrophoneEnabled(true)
        UnmuteMicrophone --> StartSpeechRecognition: Web Speech API Listen
        StartSpeechRecognition --> StartTurnTimer: Countdown (e.g. 45s)
        Note right of STATE_CANDIDATE_TURN: Mic ACTIVE 🎙️\nLive Waveform Pulses\nCandidate Speaks Answer
    }
    
    STATE_CANDIDATE_TURN --> STATE_EVALUATION_WAITING: Click "Submit Turn" OR Timer Expires
    
    state STATE_EVALUATION_WAITING {
        [*] --> MuteMicrophone: setMicrophoneEnabled(false)
        MuteMicrophone --> SendAnswerDataChannel: Publish { type: "candidate_answer" }
        SendAnswerDataChannel --> AwaitScorecard: Display "Evaluating Rubric..."
        Note right of STATE_EVALUATION_WAITING: Mic HARD-MUTED 🔇\nSTT OFF
    }
    
    STATE_EVALUATION_WAITING --> STATE_QUESTION_PLAYING: Next Question Received
    STATE_EVALUATION_WAITING --> STATE_CONCLUDED: Final Evaluation Received
    
    STATE_CONCLUDED --> [*]: View Full Report & Scorecard
```

---

## 3. Specifications & Invariants

### 3.1. Static Instruction Audio Asset
- **File Location:** `services/web_api/src/api/static/audio/interview_instructions.mp3`
- **Voice Model:** Microsoft Edge Neural TTS `en-GB-SoniaNeural` (Official British English Examiner persona)
- **Standard Script:**
  > *"Welcome to your official UKVI Credibility and Academic Admissions Interview. In this session, you will be asked a series of questions regarding your chosen course, university choice, financial readiness, and future career plans. For each question, listen carefully to the examiner. When the examiner finishes speaking, your microphone will automatically activate and the countdown timer will begin. Speak your answer clearly. When you are finished, click Submit Turn to record your response. Please ensure you are in a quiet room and speak directly into your microphone. Let us begin with your first question."*
- **Caching:** Served statically by FastAPI `StaticFiles` with `Cache-Control: public, max-age=604800` (7 days).

### 3.2. Microphone Gating Invariant
Under Constitution Article I (Sub-second Media & Data Integrity):
- At NO point while audio playback is active (`audioEl.paused === false`) shall `localParticipant.isMicrophoneEnabled` be true.
- At NO point while audio playback is active shall browser `SpeechRecognition` be running.
- This invariant guarantees zero acoustic echo, eliminates audio feedback loop pollution into candidate transcripts, and strictly prevents candidate interruption during examiner prompts.

### 3.3. Question Presentation Contract
When a `type: "question"` packet is received from the LiveKit agent worker:
```json
{
  "type": "question",
  "prompt": "Why did you choose the University of Hertfordshire over other institutions?",
  "topic_name": "Course & University Choice",
  "topic_index": 1,
  "total_topics": 3,
  "expected_time_to_ans": 45
}
```
1. If the client is currently in `STATE_INSTRUCTION`, the incoming question packet is **buffered** until the instruction audio concludes (or the candidate clicks "Proceed to Interview").
2. When transitioning to `STATE_QUESTION_PLAYING`, the `#questionPrompt` text element is immediately updated with the `prompt` string, `#topicBadge` displays the topic progression, and `/api/tts` plays the spoken prompt.
3. The `#replaySpeechBtn` allows candidates to replay the examiner's voice if needed.

---

## 4. Verification & Testing Standards
1. **Asset Integrity Test:** Verify `interview_instructions.mp3` exists, is non-empty, and returns HTTP 200 with `audio/mpeg` content-type.
2. **State Gating Test:** Ensure that upon connecting, microphone track is muted and live candidate transcript does not process ambient noise.
3. **Turn Transition Test:** Verify `audio.onended` properly transitions UI to `STATE_CANDIDATE_TURN` and enables the microphone and timer.
