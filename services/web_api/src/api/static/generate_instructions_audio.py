import asyncio
from pathlib import Path
import edge_tts

TEXT = (
    "Welcome to your official UKVI Credibility and Academic Admissions Interview. "
    "In this session, you will be asked a series of questions regarding your chosen course, "
    "university choice, financial readiness, and future career plans. "
    "For each question, listen carefully to the examiner. When the examiner finishes speaking, "
    "your microphone will automatically activate and the countdown timer will begin. "
    "Speak your answer clearly. When you are finished, click Submit Turn to record your response. "
    "Please ensure you are in a quiet room and speak directly into your microphone. "
    "Let us begin with your first question."
)

VOICE = "en-GB-SoniaNeural"
OUTPUT_DIR = Path(__file__).resolve().parent / "audio"
OUTPUT_FILE = OUTPUT_DIR / "interview_instructions.mp3"


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Synthesizing static instruction audio with voice {VOICE}...")
    communicate = edge_tts.Communicate(TEXT, VOICE)
    await communicate.save(str(OUTPUT_FILE))
    print(f"Saved static instruction audio to: {OUTPUT_FILE} ({OUTPUT_FILE.stat().st_size} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
