"""TTS service for streaming voice conversation mode."""

import re

import openai
import structlog

from app.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class TTSService:
    """Sentence-level TTS using OpenAI API."""

    def __init__(self, voice: str = "alloy", speed: float = 1.0) -> None:
        self._client = openai.AsyncOpenAI(api_key=get_settings().openai_api_key)
        self._voice = voice
        self._speed = speed

    async def synthesize_sentence(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float | None = None,
    ) -> bytes:
        """Synthesize a single sentence/chunk to MP3 bytes."""
        response = await self._client.audio.speech.create(
            model="tts-1",
            voice=voice or self._voice,
            input=text,
            speed=speed or self._speed,
            response_format="mp3",
        )
        return response.content


# Sentence boundary pattern: splits on .!? followed by whitespace
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


class SentenceAccumulator:
    """Accumulates streaming text and yields complete sentences.

    Used to batch streaming tokens into sentence-sized chunks for TTS.
    """

    def __init__(self, min_length: int = 20) -> None:
        self._buffer: str = ""
        self._min_length = min_length

    def add(self, delta: str) -> list[str]:
        """Add text delta, return list of complete sentences (if any)."""
        self._buffer += delta
        sentences: list[str] = []

        # Split on sentence boundaries
        parts = _SENTENCE_BOUNDARY.split(self._buffer)

        if len(parts) > 1:
            # All parts except last are complete sentences
            for part in parts[:-1]:
                stripped = part.strip()
                if len(stripped) >= self._min_length:
                    sentences.append(stripped)
                elif sentences:
                    # Merge short fragment with previous sentence
                    sentences[-1] += " " + stripped
                elif stripped:
                    sentences.append(stripped)
            # Keep last part in buffer (may be incomplete)
            self._buffer = parts[-1]

        return sentences

    def flush(self) -> str | None:
        """Return remaining buffer content (at stream end)."""
        remaining = self._buffer.strip()
        self._buffer = ""
        return remaining if remaining else None
