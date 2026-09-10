# FastAPI & LiveKit Direct WebRTC Architecture Guide

This guide details how to operate the UK Credibility & Academic AI Interviewer using **FastAPI** as the control plane and a **local Dockerized LiveKit instance** for direct real-time WebRTC audio and data channel communication—completely bypassing custom WebSockets.

---

## 1. Architecture Overview

```
                                  BROWSER CLIENT (React / Next.js)
                                  ┌───────────────────────────────┐
                                  │ - livekit-client SDK          │
                                  │ - Subscribes to AI TTS Audio  │
                                  │ - Publishes Mic Audio Track   │
                                  │ - Listens to DataChannel      │
                                  └───────┬───────────────┬───────┘
                                          │               │
                     1. POST /api/sessions│               │ 2. Direct WebRTC
                     2. POST /api/token   │               │    - Signaling: ws://127.0.0.1:7880
                        (LiveKit JWT)     │               │    - Media: UDP 7882
                                          ▼               ▼
                                 ┌────────────────┐ ┌─────────────────────────┐
                                 │ FastAPI Server │ │ LiveKit Server (Docker) │
                                 │ (Port 8000)    │ │ (Port 7880 / 7882 UDP)  │
                                 └────────────────┘ └────────────▲────────────┘
                                                                 │
                                                                 │ 3. Audio & Data Channel
                                                                 ▼
                                                    ┌─────────────────────────┐
                                                    │ LiveKit Agent Worker    │
                                                    │ (agent.py - LangGraph)  │
                                                    │ - Silero VAD + STT      │
                                                    │ - LangGraph Brain       │
                                                    │ - Gemini TTS            │
                                                    │ - DataChannel Broadcast │
                                                    └─────────────────────────┘
```

---

## 2. Starting the Local LiveKit Server (Docker)

1. Start the LiveKit media server:
   ```bash
   docker compose up -d
   ```
2. Verify it is running:
   ```bash
   curl -I http://localhost:7880
   ```
   LiveKit will respond on port `7880` (signaling & HTTP API) and UDP port `7882` (WebRTC media).

---

## 3. Starting the FastAPI Control Plane

FastAPI provides endpoints to create sessions, validate student CAS credentials, and issue signed LiveKit JWT AccessTokens.

Start the FastAPI development server:
```bash
uv run uvicorn src.interview.api.server:app --reload --port 8000
```

Interactive OpenAPI documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Primary Endpoints:
- `POST /api/sessions`: Creates an interview session with a student profile and target UK university.
- `POST /api/sessions/{session_id}/token`: Generates a cryptographically signed candidate LiveKit JWT AccessToken.
- `GET /api/sessions/{session_id}/status`: Queries live topic progression and scorecard metrics.
- `GET /api/sessions/{session_id}/evaluation`: Retrieves the final UKVI credibility report once completed.
- `POST /api/livekit/webhook`: Receives room lifecycle events from LiveKit server.

---

## 4. Starting the LiveKit Agent Worker

The Python agent worker connects to the local LiveKit instance and waits for interview rooms to be joined:

```bash
uv run python src/interview/live_kit/agent.py dev
```

---

## 5. Frontend Client Implementation (Direct WebRTC & Data Channel)

The frontend connects directly to LiveKit Server using the `livekit-client` npm package. No custom WebSocket connection to FastAPI is required!

### Example (TypeScript / JavaScript):

```typescript
import { Room, RoomEvent, RemoteTrack, Track } from "livekit-client";

async function joinInterview() {
  // Step 1: Initialize Session and Request JWT Token from FastAPI
  const sessionRes = await fetch("http://localhost:8000/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      student_id: "UK-CAS-2026-9041",
      university_id: "UK-HERTS-01",
      difficulty: "Medium",
    }),
  });
  const sessionData = await sessionRes.json();

  const tokenRes = await fetch(`http://localhost:8000/api/sessions/${sessionData.session_id}/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  const { token, livekit_url } = await tokenRes.json();

  // Step 2: Initialize LiveKit Room
  const room = new Room({
    adaptiveStream: true,
    dynacast: true,
  });

  // Step 3: Listen for Interviewer's Spoken Audio Track
  room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
    if (track.kind === Track.Kind.Audio) {
      const audioElement = track.attach();
      document.body.appendChild(audioElement);
      console.log("Interviewer audio track attached and playing.");
    }
  });

  // Step 4: Receive Real-Time Turn Scorecards and Final Report over DataChannel
  room.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
    const message = JSON.parse(new TextDecoder().decode(payload));
    
    if (message.type === "final_evaluation") {
      console.log("🎓 Final UKVI Evaluation Report:", message.final_evaluation);
      displayFinalReport(message.final_evaluation);
    } else {
      console.log("📊 Real-time Turn Scorecard:", message);
      updateScorecardUI({
        score: message.accuracy_score,
        passed: message.is_passed,
        reask: message.is_reask,
        matched: message.matched_keywords,
        feedback: message.feedback,
      });
    }
  });

  // Step 5: Connect directly to LiveKit Server
  await room.connect(livekit_url, token);
  console.log("Connected to room:", room.name);

  // Step 6: Enable Candidate Microphone
  await room.localParticipant.setMicrophoneEnabled(true);
  console.log("Microphone enabled. You can now speak to the AI interviewer!");
}
```
