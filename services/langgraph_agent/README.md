# LangGraph Agent & LiveKit Worker Service

Standalone cognitive engine providing:
1. `question_generation_graph`: Admin curriculum ingestion, topic & question synthesis, and review checkpoint.
2. `interview_execution_graph`: Runtime turn evaluation loop (zero on-the-fly generation).
3. LiveKit Agent Worker: Sub-second voice media processing over WebRTC with DataChannel scorecard emission.
