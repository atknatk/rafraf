"""Suggestion service — AI cevabindan sonra proaktif takip onerileri uretir."""

from __future__ import annotations

import asyncio

import anthropic
import structlog

from app.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_SYSTEM_PROMPT = (
    "Sen bir AI proje asistanisın. Kullanicinin mesaji ve AI cevabina bakarak "
    "TAM OLARAK 3 kisa, aksiyonable Turkce takip onerisi uret. "
    "Her oneri en fazla 5 kelime. "
    "Sadece onerileri listele, baska hicbir sey yazma."
)

_USER_TEMPLATE = """\
Kullanici mesaji: {user_message}

AI cevabi: {ai_response}

3 takip onerisi:"""


async def generate_suggestions(
    user_message: str,
    ai_response: str,
    project_context: str | None = None,  # noqa: ARG001 reserved for future use
) -> list[str]:
    """Haiku ile 3 kisa Turkce takip onerisi uret.

    Args:
        user_message: Kullanicinin gonderdigi mesaj.
        ai_response: AI'nin verdigi cevap.
        project_context: Opsiyonel proje baglami (kullanilmaz ama API genisletilebilir).

    Returns:
        En fazla 3 oneri stringi iceren liste. Hata durumunda bos liste.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        await logger.awarning("suggestions_skipped_no_api_key")
        return []

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        user_prompt = _USER_TEMPLATE.format(
            user_message=user_message[:500],
            ai_response=ai_response[:1000],
        )

        response = await asyncio.wait_for(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            ),
            timeout=8.0,
        )

        first_block = response.content[0] if response.content else None
        raw_text = (
            first_block.text if first_block is not None and hasattr(first_block, "text") else ""
        )
        suggestions = _parse_suggestions(raw_text)
        await logger.adebug("suggestions_generated", count=len(suggestions))
        return suggestions

    except TimeoutError:
        await logger.awarning("suggestions_timeout")
        return []
    except Exception:
        await logger.awarning("suggestions_generation_failed")
        return []


def _parse_suggestions(raw: str) -> list[str]:
    """'1. ...\\n2. ...\\n3. ...' formatindaki metni ayristir."""
    results: list[str] = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # "1. ", "2. ", "3. " gibi on ekleri kaldir
        for prefix in ("1. ", "2. ", "3. ", "1) ", "2) ", "3) ", "- "):
            if line.startswith(prefix):
                line = line[len(prefix) :]
                break
        if line:
            results.append(line)
        if len(results) == 3:
            break
    return results
