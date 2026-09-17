import hashlib
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response, status

logger = logging.getLogger("tts_router")

router = APIRouter(tags=["Text to Speech"])

# In-memory audio cache: MD5(voice + text) -> bytes
_TTS_CACHE: dict[str, bytes] = {}
_MAX_CACHE_ENTRIES = 200

# Default British English neural voice for UKVI Credibility examiner
DEFAULT_UK_VOICE = "en-GB-SoniaNeural"


@router.get("/tts")
async def generate_speech_audio(
    text: str = Query(..., min_length=1, max_length=1500, description="Text prompt to synthesize"),
    voice: Optional[str] = Query(None, description="Neural voice identifier (defaults to en-GB-SoniaNeural)"),
):
    """
    Synthesizes natural British English voice audio for UKVI examiner questions.
    Returns streaming audio/mpeg with in-memory caching for minimal latency.
    """
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text parameter cannot be empty.")

    target_voice = (voice or DEFAULT_UK_VOICE).strip()
    cache_key = hashlib.md5(f"{target_voice}::{clean_text}".encode("utf-8")).hexdigest()

    if cache_key in _TTS_CACHE:
        return Response(
            content=_TTS_CACHE[cache_key],
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-TTS-Cache": "HIT",
            },
        )

    try:
        import edge_tts

        communicate = edge_tts.Communicate(clean_text, target_voice)
        audio_buffer = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.extend(chunk["data"])

        if not audio_buffer:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No audio returned from TTS engine.")

        audio_bytes = bytes(audio_buffer)

        # Cache management
        if len(_TTS_CACHE) >= _MAX_CACHE_ENTRIES:
            # Drop earliest inserted key
            first_key = next(iter(_TTS_CACHE))
            _TTS_CACHE.pop(first_key, None)
        _TTS_CACHE[cache_key] = audio_bytes

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-TTS-Cache": "MISS",
            },
        )

    except Exception as exc:
        logger.warning("TTS audio generation failed for '%s': %s", clean_text[:40], exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neural TTS engine unavailable: {exc}",
        )
