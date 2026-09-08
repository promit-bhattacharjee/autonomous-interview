# Product Requirements Document (PRD)
# UK Credibility & Academic Voice Interview Agent

**Document Version:** 1.0.0  
**Status:** Approved / Draft Architecture  
**Core Framework:** Spec-Driven Architecture & Constitution Governance  
**Target Environment:** Local LiveKit (Zero Cloud Fees) + LangGraph Brain + FastAPI Backend  

---

## 1. Executive Summary & Product Mission

The **UK Credibility & Academic Voice Interview Agent** is an autonomous AI-driven interviewer designed to assess international students applying for UK higher education institutions and UK Student Visas (Credibility Interviews).

The agent evaluates:
1. **Academic Genuine Intent:** Knowledge of course modules, university choice rationale, career trajectory.
2. **Financial Credibility:** Awareness of tuition costs, accommodation fees, living expenses, and sponsor funding.
3. **Language & Communication:** Spoken fluency, technical keyword accuracy, and conversational consistency.

The system is architected around **Zero LiveKit Cloud Fees** (running a local LiveKit WebRTC server) combined with **Bring-Your-Own-Key (BYOK)** models (Google Speech STT/TTS and Gemini LLM).

---

## 2. User Roles & Persona Specifications

```
                       ┌──────────────────────────────────────────────┐
                       │               SYSTEM USERS                   │
                       └──────────────────────┬───────────────────────┘
                                              │
                     ┌────────────────────────┴────────────────────────┐
                     ▼                                                 ▼
        ┌─────────────────────────┐                       ┌─────────────────────────┐
        │      ADMIN USER         │                       │      STUDENT USER       │
        │ - Uploads Question Bank │                       │ - Enters Profile/CAS    │
        │ - Configures Rubrics    │                       │ - Joins Voice Session   │
        │ - Sets Thresholds (70%) │                       │ - Real-Time Q&A Speech  │
        │ - Reviews Transcripts   │                       │ - Views Scorecard       │
        └─────────────────────────┘                       └─────────────────────────┘
```

### 2.1. Admin Role
- **Question File Ingestion:** Admin uploads structured or unstructured question files (PDF, DOCX, TXT, JSON) containing interview questions, topics, criteria, and expected answer keywords.
- **Rubric & Difficulty Configuration:** Defines passing thresholds (default $\ge 70\%$), re-ask allowances (1 re-ask on low score), and expected answer duration.
- **Session Audit & Analytics:** Views candidate accuracy scorecards, keyword hit/miss records, and complete conversation audio transcripts.

### 2.2. Student Role
- **Profile Submission:** Provides core context (Target UK University, Course, Previous Degree/GPA, English Proficiency, Sponsor Details).
- **Interactive Voice Interview:** Connects to an audio-only WebRTC room, hears questions spoken naturally via Google TTS, and responds through their microphone via Google STT.
- **Dynamic Feedback:** Receives natural re-asks if an answer is incomplete, follow-up probe questions, and a concluding evaluation.

---

## 3. System Architecture & Component Decoupling

The platform adheres to a strict separation of concerns across three layers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        1. API & STORAGE LAYER                          │
│  FastAPI (Upcoming)                                                    │
│  - Admin: Uploads question file -> Stored in session repository        │
│  - Student: Requests session -> Merges Student Profile + Questions     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Initial Text & Structured Plan
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        2. THE BRAIN (LangGraph)                        │
│  interview_graph & nodes.py                                            │
│  - extract_initial_text: Normalizes Student Info + Admin Questions     │
│  - generate_questions: Builds Topics, Questions, & Rubric Keywords     │
│  - evaluate_answer: Compares candidate text with expected keywords    │
│  - process_answer: State machine (Re-ask once if < 70%, next Q)       │
│  - ask_question: Formulates speech text for the interviewer            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Turn Strings (Q&A)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 3. VOICE COMMUNICATOR (Local LiveKit)                  │
│  Zero Paid Cloud Endpoints (Self-Hosted LiveKit Server)                │
│  - Ear: Silero VAD (Local CPU) + Google STT                            │
│  - Mouth: Google TTS (Journey Voice)                                   │
│  - Data Channel: Emits real-time scores & keyword tags to UI           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Data Specification: What is "Initial Text"?

When an interview session is created, the system synthesizes two documents into the **Initial Text Payload**:

### 4.1. Student Profile Data
```json
{
  "student_id": "STU-88219",
  "full_name": "Candidate Name",
  "target_country": "United Kingdom",
  "target_university": "University of Hertfordshire",
  "target_course": "MSc Artificial Intelligence with Advanced Research",
  "academic_background": "BSc in Computer Science, CGPA 3.65/4.0",
  "ielts_score": "7.5 (L:8.0, R:7.5, W:7.0, S:7.5)",
  "tuition_fee_gbp": 16500,
  "living_cost_gbp": 12500,
  "sponsor": "Self-funded and Parents savings (£32,000 in bank deposit)",
  "post_study_plan": "Return to home country to work as an AI Solutions Architect"
}
```

### 4.2. Admin Question Bank Document
```text
Topic 1: Course & University Choice
- Why Hertfordshire over other UK universities like Manchester or Queen Mary?
  Keywords: campus facilities, specific module curriculum, robotics lab, tuition affordability
- How does this specific master's degree align with your previous degree?
  Keywords: machine learning foundation, programming, research thesis

Topic 2: Financial Capability & Living Costs
- What is the total cost of your studies including living expenses, and who is paying?
  Keywords: 16500 tuition, living expenses, bank balance, parental sponsor, funds held 28 days

Topic 3: Post-Study Intentions (UK Credibility Rule)
- What are your career intentions after completing this course in the UK?
  Keywords: return to home country, career opportunities, software industry, salary growth
```

### 4.3. Combined Initial Input State
The initial text payload sent to `interview_graph` merges both:
$$\text{extraced\_text} = \text{Student Profile Data} + \text{Admin Question Document}$$

---

## 5. Specification Kit & Constitution Framework

To maintain software reliability and prevent architectural drift, the project is governed by the **Specs Constitution**:

### Principle I: Zero LiveKit Cloud Dependency
The system MUST run exclusively on local LiveKit instances (`ws://127.0.0.1:7880`, `devkey`/`secret`) or self-hosted media servers. No paid LiveKit Cloud subscription APIs shall be introduced.

### Principle II: Complete Decoupling of Voice and Brain
LiveKit is strictly an **Audio Communicator**. It must never contain business logic, rubric scoring, or interview question arrays. All conversational state belongs in `InterviewSession` and LangGraph.

### Principle III: Objective Keyword Rubrics ($\ge 70\%$ Rule)
Every interview question MUST be bound to `expected_answer_keywords`. The candidate's response is scored $0.0$ to $100.0\%$. 
- Score $< 70\%$ on Attempt 1 $\implies$ Trigger polite **Re-ask** targeting missed keywords.
- Score $\ge 70\%$ or Attempt 2 completed $\implies$ Advance to follow-up or next main question.

### Principle IV: Incremental Feature Delivery
1. **Terminal Mode Prototype** (Validate state transitions and document synthesis locally).
2. **FastAPI Endpoints** (Admin file upload and Student session creation).
3. **WebRTC Voice Gateway** (LiveKit audio streaming).
4. **Client Interface** (React/Next.js dashboard).

---

## 6. Terminal Architecture Specification (Immediate Phase)

Before implementing FastAPI HTTP routes, the system operates in **Terminal Execution Mode**:

### Workflow:
1. Load student profile context from a local configuration or mock object.
2. Ingest question file from a local document (e.g. `data/questions/uk_visa_rubric.txt`).
3. Initialize `InterviewSession` with the combined initial state.
4. Run interactive turn-by-turn CLI:
   - Interviewer questions printed to terminal.
   - Candidate types answer (or speaks through local microphone).
   - Accurate evaluation scorecard printed on every turn (Accuracy %, Matched keywords, Unmatched keywords, Re-ask status).
