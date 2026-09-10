# System Constitution & Technical Governance

**Document Version:** 2.2.0  
**Governing Document:** [product_requirement.md](file:///c:/Users/promi/OneDrive/Desktop/interviewv2/product_requirement.md)  
**Spec Kit Root:** `docs/specs/`  
**Domain Focus:** UKVI & Academic Immigration Credibility Interview System  
**Last Updated:** 2026-09-11  

---

## Article I: The Inviolable Core Principles

### 1. Self-Hosted Audio Media & Direct WebRTC (Zero Cloud Fees)
- The platform MUST run on open-source, local LiveKit server instances (`ws://127.0.0.1:7880`) in development and self-hosted SFU nodes in production.
- Under no circumstances shall proprietary LiveKit Cloud API keys or paid endpoints be introduced.
- Clients connect **directly to LiveKit Server** via WebRTC (signaling on port 7880, UDP media on 7882). Custom raw WebSockets on FastAPI for audio streaming are strictly forbidden.

### 2. Multi-Tier Decoupled Architecture
- **Transport Layer (LiveKit):** Strictly real-time WebRTC media (Microphone $\to$ STT; Text $\to$ TTS) and live scorecard DataChannels.
- **Orchestration & Presentation Layer (FastAPI + Jinja2 SSR):** Role-based session management, authentication, and Server-Side Rendered (SSR) portals for Admin and Student.
- **Persistence Layer (SQLAlchemy ORM):** SQLite for local development with strict declarative models engineered for seamless production migration to MySQL.
- **Cognitive Layer (LangGraph):** Decoupled into two separate graphs: Question Generation vs. Interview Execution.

### 3. Two Decoupled Graphs Architecture (Generation vs. Execution)
The system MUST NOT bundle question generation and live interview execution into a single graph. They are strictly decoupled into two isolated state graphs:
- **`question_generation_graph` (Admin Workflow):** 
  - Triggered when Admin uploads text/curriculum and selects a tier (`Easy`, `Medium`, `Hard`).
  - Generates topic structures, questions, and follow-up probes segmented for administrative inspection.
  - Suspends at an **Admin Review Checkpoint**: the admin reviews the generated segments on screen, confirms/edits questions, modifies follow-up probes, and refines rubric keywords.
  - Persists the confirmed question set to SQLite.
- **`interview_execution_graph` (Student Workflow):**
  - Strictly executes turn-by-turn conversational loops (`evaluate_answer -> process_answer -> ask_question -> generate_final_evaluation`).
  - **NEVER generates questions on the fly.**
  - Operates purely on pre-approved, admin-confirmed questions assigned to the candidate.

### 4. Reusable Multi-Tier Question Banks (Easy / Medium / Hard)
- Question sets run for multi-month admissions cycles (4–5 months). One question bank can be linked to multiple students (1-to-many relationship).
- Cache-First: Once generated and approved by an Admin, question banks are served directly from SQLite without recurring LLM generation costs.
- **Auto-Deactivation Invariant:** When an admin assigns a new Question Bank to a student who already has one, the system automatically deactivates and replaces the previous bank for that student, strictly guaranteeing at most 1 active bank per candidate.
- Immigration Credibility Focus: Rubrics strictly evaluate UKVI genuine student criteria: academic intent, course module mastery, 28-day financial maintenance rules, and post-study home ties.

### 5. Strict Pre-Assignment Gate & One-Bank-Per-User Rule
- Before an interview can start, a candidate MUST have an approved Question Bank explicitly assigned to them.
- **One User, One Bank:** A student can have only ONE active Question Bank assigned at any given time.
- If no question bank is assigned, the system strictly forbids interview session generation ("Before that, no interview will be generated").

### 6. Service / Repository Pattern & Modular Relational Ingestion
- **Single Source of Truth:** Relational navigation for question banks, topics, questions, and follow-ups is governed by an in-process **Service / Repository Layer** (`src/interview/services/question_service.py`) using SQLAlchemy ORM.
- **Dual Ingress Consumption:**
  1. **Browser / Web UI (Over Network):** Consumes standard FastAPI REST endpoints (`/api/banks/{id}/topics`, etc.) for dynamic UI rendering.
  2. **LangGraph Agent & LiveKit Worker (In-Process):** Strictly invokes the Python Service functions directly (`fetch_topics`, `fetch_questions`, `fetch_followups`, `get_user_assigned_questions`) using local session contexts.
- **Zero Loopback Rule:** In-process agents MUST NEVER make HTTP loopback requests (`localhost:8000/api/...`) to their own server. Direct ORM invocation guarantees **sub-millisecond execution (< 0.1ms)**, prevents socket exhaustion, and eliminates network serialization latency during active voice turns.

### 7. Ingress Boundary Validation (Pydantic v2)
- Validation is strictly enforced at the ingress boundary (FastAPI layer using Pydantic schemas).
- Malformed or incomplete student profiles, university parameters, or rubric submissions are rejected immediately (HTTP 422 Unprocessable Entity) before reaching the database or graph.

### 8. Encrypted Credential Vault & Multi-Provider Matrix (BYOK)
- Plaintext API keys MUST NEVER be stored in the database.
- **Supported Providers:** Google (Gemini, Google Speech), OpenRouter, Ollama, DeepSeek, GLM, and Grok (xAI).
- **Capability Mapping:** Providers can be configured for Thinking (LLM reasoning), Speech-to-Text (STT), and Text-to-Speech (TTS).
- **Authority Hierarchy:**
  - If the Admin provides the key, the Admin strictly selects and configures the provider, models, and capabilities (students cannot override).
  - If the Student provides their own API key (BYOK), the student selects their preferred provider and credentials.
- All keys are encrypted at rest using symmetric encryption (**Fernet / AES-256**) and decrypted strictly in-memory during outbound API calls.
- Masked previews (e.g., `sk-...3x91`) are enforced across all user interfaces.

### 9. Rubric-Driven Evaluation ($\ge 70\%$ Gate)
- Every candidate response is evaluated against explicit expected keywords and concept coverage ($0.0$ to $100.0\%$).
- If a candidate's score is $< 70\%$ on Attempt 1, the agent MUST issue a polite, targeted re-ask targeting missed keywords before advancing.
- On Attempt 2 or when score $\ge 70\%$, the system progresses through follow-ups or advances to the next topic.

### 10. Mid-Interview Disconnect & Token Runout Discard Policy
- If a candidate loses network connection (WebRTC disconnect event) or if an LLM token budget is exhausted during an active interview, the session MUST be cleanly aborted and partial/corrupted data **discarded**.
- Only fully completed interviews with verified turn progression are finalized and committed as permanent evaluation records.

### 11. Server-Side Rendered (SSR) Portals with Local Bootstrap
- The user interface operates via FastAPI Server-Side Rendering (Jinja2 templates).
- Styling is powered by **Local Bootstrap** assets (`bootstrap.min.css` and `bootstrap.bundle.min.js`) bundled locally in `static/` (zero external CDN latency, zero complex npm build pipelines).

### 12. JWT Cookie Authentication Middleware & 10-Day Expiry with Device Lockdown
- Authentication tokens are issued as cryptographically signed JSON Web Tokens (JWT) stored in secure HTTP-only cookies (`access_token`) with a **10-day validity window**.
- **Middleware Control:** A centralized FastAPI middleware handles token retrieval from the cookie, expiration verification, and device ID validation.
- If the token expires, the cookie is cleared and the user is redirected to `/login`.
- **Single-Device Lockdown:** 
  - Every login binds a `device_id` into the user's SQLite record and the JWT claims.
  - The middleware verifies that `token.device_id == user.active_device_id`.
  - If a user logs in from a new device, the database record is overwritten with the new `device_id`, instantly terminating the session on the prior device (redirecting the prior device to `/login`).

### 13. Open Repository Data Protection (Zero SQLite / Secret Commits)
- Because this is an open repository, SQLite database files (`*.db`, `*.sqlite`, `*.sqlite3`), session stores, and environment secrets must NEVER be tracked or committed to GitHub.
- Strict `.gitignore` rules and automated repository integrity checks prevent partial or direct data leakage.

---

## Article II: Role & Feature Specification Matrix

| Role | Code | Feature Name | Governing Spec | Implementation Status |
|---|---|---|---|---|
| **Admin** | `ADM-01` | Upload & Manage UK Universities in SQLite | `SPEC-003` | Proposed / In-Review |
| **Admin** | `ADM-02` | Configure Model Providers & Encrypted Keys (OpenRouter, Groq, Ollama) | `SPEC-002` | Proposed / In-Review |
| **Admin** | `ADM-03` | Dedicated `question_generation_graph` Execution & Segmentation | `SPEC-003` | Proposed / In-Review |
| **Admin** | `ADM-04` | Review Checkpoint & Tree-View Editor (Confirm, Edit Questions/Follow-ups) | `SPEC-003` | Proposed / In-Review |
| **Admin** | `ADM-05` | Candidate Assignment Matrix (Assign 1 Bank per User, Global / Exclusion) | `SPEC-003` | Proposed / In-Review |
| **Admin** | `ADM-06` | Audit Candidate Evaluation Scorecards & UKVI Recommendations | `SPEC-003` | Proposed / In-Review |
| **Student** | `STU-01` | Account Registration & Authentication (SSR Session Auth) | `SPEC-004` | Proposed / In-Review |
| **Student** | `STU-02` | CAS Profile Submission (Academic, Financial, Sponsor Data) | `SPEC-004` | Proposed / In-Review |
| **Student** | `STU-03` | Target University Selection (from Admin-Approved Institutions) | `SPEC-004` | Proposed / In-Review |
| **Student** | `STU-04` | Optional BYOK API Key Configuration (Encrypted Vault) | `SPEC-002` / `SPEC-004` | Proposed / In-Review |
| **Student** | `STU-05` | Pre-Interview Assignment Check (Requires Confirmed Question Bank) | `SPEC-004` / `SPEC-005` | Proposed / In-Review |
| **Student** | `STU-06` | Real-Time Voice Interview via `interview_execution_graph` (LiveKit WebRTC) | `SPEC-005` | Prototype Ready |
| **Student** | `STU-07` | View Official Credibility Report & Topic Breakdown | `SPEC-004` / `SPEC-005` | Proposed / In-Review |
| **System** | `SYS-01` | SQLAlchemy Relational Persistence (SQLite $\to$ MySQL Ready) | `SPEC-002` | Proposed / In-Review |
| **System** | `SYS-02` | Fernet/AES-256 Symmetric Credential Encryption Vault | `SPEC-002` | Proposed / In-Review |
| **System** | `SYS-03` | Tool-Based Relational Fetching Endpoints (Topics, Questions, Followups) | `SPEC-002` / `SPEC-003` | Proposed / In-Review |
| **System** | `SYS-04` | Mid-Interview Disconnect & Token Runout Discard Guard | `SPEC-005` | Proposed / In-Review |
| **System** | `SYS-05` | Local Bootstrap SSR Presentation Engine | `SPEC-003` / `SPEC-004` | Proposed / In-Review |
| **System** | `SYS-06` | JWT Authentication & Single-Device Lockdown (`device_id` Invariant) | `SPEC-002` / `SPEC-004` | Proposed / In-Review |

---

## Article III: Spec-Driven Change Protocol (GitHub Spec Kit)

To maintain software reliability and prevent architectural drift:
1. **Define Specification:** Every feature or domain application is defined in a formal document under `docs/specs/SPEC-XXX-<title>.md`.
2. **Constitutional Alignment:** The feature code and governance rules are cross-referenced in this Constitution matrix.
3. **Two-Graph Separation:** Question generation features belong exclusively to `SPEC-003` (`question_generation_graph`); interview turn features belong exclusively to `SPEC-005` (`interview_execution_graph`).
4. **Tool-Based Verification:** Tools fetching topics, questions, and follow-ups are verified with unit tests before graph integration.
5. **Security Enforcement:** All session ingress points enforce JWT token authenticity and single `device_id` integrity.
6. **Integration Pipeline:** Automated end-to-end testing verifies the contract before release.
