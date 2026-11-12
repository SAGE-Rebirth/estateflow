"""Google Gemini: one place for the shared client and the small media helpers
(speech-to-text, image description)."""

from functools import lru_cache

import structlog
from google import genai
from google.genai import types

from app.core.config import get_settings

log = structlog.get_logger()


@lru_cache
def gemini_client() -> genai.Client:
    s = get_settings()
    return genai.Client(
        api_key=s.gemini_api_key,
        http_options=types.HttpOptions(
            timeout=int(s.gemini_timeout_seconds * 1000),
            # One retry for 429/5xx; anything else surfaces immediately.
            retry_options=types.HttpRetryOptions(attempts=2),
        ),
    )


async def _describe(data: bytes, mime: str, prompt: str, max_tokens: int) -> str | None:
    s = get_settings()
    response = await gemini_client().aio.models.generate_content(
        model=s.gemini_media_model,
        contents=[types.Part.from_bytes(data=data, mime_type=mime), prompt],
        config=types.GenerateContentConfig(max_output_tokens=max_tokens),
    )
    text = (response.text or "").strip()
    return text or None


TRANSCRIBE_PROMPT = (
    "Transcribe this WhatsApp voice note verbatim, in the language it was spoken. "
    "Reply with the transcript only. If there is no speech, reply with nothing."
)


async def transcribe(audio: bytes, mime: str = "audio/ogg") -> str | None:
    """Voice note → text. None when disabled or the call fails."""
    s = get_settings()
    if not s.transcribe_voice_notes or not s.gemini_api_key:
        return None
    try:
        return await _describe(audio, mime.split(";")[0], TRANSCRIBE_PROMPT, 1024)
    except Exception as exc:  # provider errors must never break message handling
        log.warning("transcription_failed", error=str(exc)[:200])
        return None


IMAGE_PROMPT = (
    "A prospective property buyer sent this photo on WhatsApp. In one or two sentences, "
    "describe what it shows that matters for a real estate conversation (e.g. a listing "
    "screenshot with its price or ref code, a floor plan, a building, a document, a "
    "location). Transcribe any visible ref codes, prices or addresses exactly."
)


async def describe_image(data: bytes, mime: str) -> str | None:
    s = get_settings()
    if not s.describe_images or not s.gemini_api_key:
        return None
    try:
        return await _describe(data, mime, IMAGE_PROMPT, 300)
    except Exception as exc:
        log.warning("image_description_failed", error=str(exc)[:200])
        return None
