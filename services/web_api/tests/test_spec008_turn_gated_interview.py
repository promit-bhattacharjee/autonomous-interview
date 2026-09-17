from pathlib import Path
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_static_instruction_audio_file_exists():
    """Verify that the pre-rendered static instruction audio file exists and is valid."""
    audio_path = Path(__file__).resolve().parent.parent / "src" / "api" / "static" / "audio" / "interview_instructions.mp3"
    assert audio_path.exists(), f"Static instruction audio file missing at {audio_path}"
    assert audio_path.stat().st_size > 50_000, f"Static instruction audio file too small: {audio_path.stat().st_size} bytes"


def test_static_instruction_audio_endpoint():
    """Verify that FastAPI static mount serves the instruction audio file correctly."""
    response = client.get("/static/audio/interview_instructions.mp3")
    assert response.status_code == 200
    assert "audio/mpeg" in response.headers.get("content-type", "")
    assert len(response.content) > 50_000


def test_interview_template_contains_spec008_elements():
    """Verify that interview.html contains the SPEC-008 FSM, instruction briefing, and mic gating elements."""
    template_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "api"
        / "templates"
        / "student"
        / "interview.html"
    )
    assert template_path.exists(), f"Template missing at {template_path}"
    content = template_path.read_text(encoding="utf-8")

    # Verify FSM and state definitions
    assert "Strict Turn-Based Finite State Machine (SPEC-008)" in content
    assert "INSTRUCTION" in content
    assert "QUESTION_PLAYING" in content
    assert "CANDIDATE_TURN" in content
    assert "EVALUATION_WAITING" in content

    # Verify UI elements
    assert 'id="promptBoxHeader"' in content
    assert 'id="skipInstructionBtn"' in content
    assert 'id="examinerSpeakingText"' in content

    # Verify static audio reference and mic gating
    assert "/static/audio/interview_instructions.mp3" in content
    assert "setMicActive(false)" in content
    assert "enterInstructionPhase()" in content
    assert "enterCandidateTurn" in content
