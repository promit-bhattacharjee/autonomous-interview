# System Constitution & Technical Governance

**Document Version:** 1.1.0  
**Governing Document:** [product_requirement.md](file:///c:/Users/promi/OneDrive/Desktop/interviewv2/product_requirement.md)  

---

## Article I: The Inviolable Core Principles

1. **Self-Hosted Audio Media (Zero Cloud Fees):**
   - The platform MUST use open-source, local LiveKit server instances (`ws://127.0.0.1:7880`) in development and self-hosted SFU nodes in production.
   - Under no circumstances shall proprietary LiveKit Cloud API keys or paid endpoints be required.

2. **Decoupled Architecture:**
   - **Transport Layer (LiveKit):** Strictly an Audio Communicator (Microphone $\to$ STT $\to$ Text; Text $\to$ TTS $\to$ Speaker).
   - **Orchestration Layer (FastAPI):** Strictly session dispatch, auth, and question file ingestion.
   - **Cognitive Layer (LangGraph):** The single source of truth for conversational turns, rubric evaluations, re-asks, and question sequencing.

3. **Rubric-Driven Evaluation ($\ge 70\%$ Gate):**
   - Every candidate response is evaluated against explicit keywords and conceptual coverage.
   - If a score is $< 70\%$ on attempt 1, the agent MUST issue a targeted re-ask before advancing.

4. **Standardized LangGraph Nodes & Pure State Processing:**
   - Graph nodes MUST be pure state transformers that operate strictly on the relational `InterviewState`.
   - Nodes MUST NOT call mock APIs, external HTTP endpoints, or database connectors directly. All data ingestion, relational DB queries, or API calls must occur prior to graph invocation in the orchestration/service layer.

5. **Ingress Boundary Validation (FastAPI & Pydantic):**
   - Validation is strictly enforced at the ingress boundary (FastAPI layer using Pydantic models `StudentData`, `UniversityData`).
   - If incoming candidate or institution data is incomplete, malformed, or missing required fields, Pydantic immediately rejects the request (HTTP 422 Unprocessable Entity) and terminates the session before graph execution.
   - LangGraph nodes MUST NOT contain redundant in-node defensive validation loops or duplicate validation dictionaries; they operate with confidence on pre-validated state.

6. **Relational State Consistency (No Redundant Serialization):**
   - Graph state maintains clean relational data structures (native dictionaries/records).
   - Nodes MUST NOT rely on redundant Pydantic conversion cycles (`model_dump()`, custom `_serialize_model()`, or manual repetitive `getattr()` checks), preserving standardized data formats directly.

7. **Static Model Configuration (.env Driven):**
   - Model specifications are statically configured via environment variables (`.env`) and static factory initializers.
   - Thinking LLM defaults to OpenRouter DeepSeek V4 Flash 0731 with automated fallback to LLaMA-3.3-70B.
   - Conversational Speech LLM defaults to Google Gemini.
   - The graph does not require dynamic model initialization gates; routing proceeds directly from `START` to core turn nodes.

---

## Article II: Role & Feature Specification Matrix

| Role | Feature Code | Feature Name | Specification Status | Implementation Status |
|---|---|---|---|---|
| **Admin** | `ADM-01` | Upload Question Bank File | Specified in `product_requirement.md` §2.1 | Terminal Mode Ready |
| **Admin** | `ADM-02` | Configure Evaluation Rubric | Specified in `product_requirement.md` §2.1 | Complete in Graph |
| **Admin** | `ADM-03` | View Candidate Scorecards | Specified in `product_requirement.md` §2.1 | Terminal & Data Channel Ready |
| **Student** | `STU-01` | Submit UK Credibility Profile | Specified in `product_requirement.md` §4.1 | Schema Implemented |
| **Student** | `STU-02` | Terminal Interactive Interview | Specified in `product_requirement.md` §6 | Complete |
| **Student** | `STU-03` | Real-Time Voice Interview (LiveKit) | Specified in `product_requirement.md` §3 | Audio Communicator Ready |
| **System** | `SYS-01` | Document & Profile Fusion | Specified in `product_requirement.md` §4.3 | Complete |
| **System** | `SYS-02` | Standardized Relational State Validation & Pure Node Isolation | Specified in User Directive & System Governance | Complete |
| **System** | `SYS-03` | Dynamic Multi-Model & Multi-Fallback Orchestration | Specified in User Directive & System Governance | Complete |

---

## Article III: Spec-Driven Change Protocol

When a new feature or role modification is requested:
1. **Define Specification:** The requirement is documented in [product_requirement.md](file:///c:/Users/promi/OneDrive/Desktop/interviewv2/product_requirement.md).
2. **Update Constitution:** The feature code and rule set are added to this matrix.
3. **Implement Isolated Unit:** Implement the feature in the cognitive or service layer.
4. **Terminal Verification:** Verify via terminal before exposing via FastAPI endpoints.

