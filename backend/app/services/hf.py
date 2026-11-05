"""Hugging Face Inference Providers: one place for the shared client and the small media
helpers (speech-to-text, image description)."""

import base64

import structlog
from huggingface_hub import AsyncInferenceClient

from app.core.config import get_settings

log = structlog.get_logger()


def hf_client(provider: str | None = None) -> AsyncInferenceClient:
    s = get_settings()
    return AsyncInferenceClient(
        provider=provider or s.hf_provider,  # type: ignore[arg-type]
        api_key=s.hf_token,
        timeout=s.hf_timeout_seconds,
    )


async def transcribe(audio: bytes) -> str | None:
    """Voice note → text with Whisper. None when disabled or the call fails."""
    s = get_settings()
    if not s.transcribe_voice_notes or not s.hf_token:
        return None
    try:
        result = await hf_client().automatic_speech_recognition(audio, model=s.hf_asr_model)
    except Exception as exc:  # provider errors must never break message handling
        log.warning("transcription_failed", error=str(exc)[:200])
        return None
    text = (result.text or "").strip()
    return text or None


IMAGE_PROMPT = (
    "A prospective property buyer sent this photo on WhatsApp. In one or two sentences, "
    "describe what it shows that matters for a real estate conversation (e.g. a listing "
    "screenshot with its price or ref code, a floor plan, a building, a document, a "
    "location). Transcribe any visible ref codes, prices or addresses exactly."
)


async def describe_image(data: bytes, mime: str) -> str | None:
    s = get_settings()
    if not s.describe_images or not s.hf_token:
        return None
    url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    try:
        out = await hf_client().chat_completion(
            model=s.hf_vision_model,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": url}},
                        {"type": "text", "text": IMAGE_PROMPT},
                    ],
                }
            ],
        )
    except Exception as exc:
        log.warning("image_description_failed", error=str(exc)[:200])
        return None
    text = (out.choices[0].message.content or "").strip()
    return text or None
