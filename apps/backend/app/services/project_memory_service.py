"""Project memory service with automatic fact extraction.

Handles project-level memory operations including automatic extraction
of structured project facts from conversation messages using Claude AI.
"""

import json
import uuid

import structlog

from app.core.config import get_settings
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import (
    ExtractedFact,
    FactExtractionResponse,
    ProjectMemoryResponse,
    ProjectSummaryResponse,
    StaleCleanupResponse,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Confidence defaults per source type
_CONFIDENCE_USER_STATED = 1.0
_CONFIDENCE_TOOL_RESULT = 0.9
_CONFIDENCE_AI_INFERRED = 0.7

# Stale threshold default
_DEFAULT_STALE_DAYS = 30

# Valid categories for fact extraction
VALID_CATEGORIES = frozenset(
    {
        "tech_stack",
        "known_issues",
        "deployment",
        "architecture_decisions",
        "preferences",
        "status",
    }
)

# Fact extraction system prompt
_EXTRACTION_SYSTEM_PROMPT = """\
Sen bir proje bilgi cikarma asistanisin. \
Verilen konusma mesajlarindan proje hakkinda \
yapisal bilgiler cikar.

Her cikarilan bilgi icin su formatta JSON dondur:
{
  "facts": [
    {
      "category": "<kategori>",
      "key": "<anahtar>",
      "value": {<yapisal_deger>},
      "confidence": <0.0-1.0>
    }
  ]
}

Gecerli kategoriler:
- tech_stack: Teknoloji bilgileri (framework, dil, vb.)
- known_issues: Bilinen sorunlar ve buglar
- deployment: Deploy bilgileri (ortam, versiyon, tarih)
- architecture_decisions: Mimari kararlar ve sebebleri
- preferences: Proje tercihleri (kod stili, araclar, vb.)
- status: Proje durumu (aktif/pasif, sprint, deadline)

Kurallar:
- Sadece acikca belirtilen bilgileri cikar
- Spekulatif bilgi cikarma
- Confidence: kesin=0.9, guclu cikarim=0.7, zayif=0.5
- Her key 100 karakter ile sinirli
- Bos facts dizisi dondur eger bilgi yoksa
- SADECE JSON formatinda yanit ver"""


class ProjectMemoryServiceError(Exception):
    """Raised when a project memory operation fails."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


class ProjectMemoryService:
    """Service for project memory operations with AI-powered fact extraction.

    Handles search, summary, stale management, and automatic extraction
    of structured project facts from conversation messages.
    """

    def _get_confidence_for_source(self, source: str) -> float:
        """Return default confidence score based on source type.

        Args:
            source: Source identifier (user_stated, tool_result, ai_inferred).

        Returns:
            Default confidence score for the source type.
        """
        confidence_map: dict[str, float] = {
            "user_stated": _CONFIDENCE_USER_STATED,
            "tool_result": _CONFIDENCE_TOOL_RESULT,
            "ai_inferred": _CONFIDENCE_AI_INFERRED,
        }
        return confidence_map.get(source, _CONFIDENCE_AI_INFERRED)

    async def search_project_memories(
        self,
        repo: MemoryRepository,
        project_id: uuid.UUID,
        query: str | None = None,
        category: str | None = None,
        min_confidence: float = 0.0,
    ) -> list[ProjectMemoryResponse]:
        """Search project memories with text query and filters.

        Args:
            repo: Memory repository instance.
            project_id: Project UUID.
            query: Optional text query.
            category: Optional category filter.
            min_confidence: Minimum confidence threshold.

        Returns:
            List of matching ProjectMemoryResponse.
        """
        rows = await repo.search(
            project_id=project_id,
            query=query,
            category=category,
            min_confidence=min_confidence,
        )
        return [
            ProjectMemoryResponse(
                id=row.id,
                project_id=row.project_id,
                category=row.category,
                key=row.key,
                value=row.value,
                confidence=row.confidence,
                source=row.source,
                last_verified_at=row.last_verified_at,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def get_project_summary(
        self,
        repo: MemoryRepository,
        project_id: uuid.UUID,
    ) -> ProjectSummaryResponse:
        """Build a comprehensive project memory summary.

        Args:
            repo: Memory repository instance.
            project_id: Project UUID.

        Returns:
            ProjectSummaryResponse with categories, totals, and stale count.
        """
        grouped = await repo.get_all_grouped_by_category(project_id)
        stale_count = await repo.count_stale_entries(project_id, _DEFAULT_STALE_DAYS)

        categories: dict[str, list[ProjectMemoryResponse]] = {}
        total_memories = 0

        for category_name, rows in grouped.items():
            categories[category_name] = [
                ProjectMemoryResponse(
                    id=row.id,
                    project_id=row.project_id,
                    category=row.category,
                    key=row.key,
                    value=row.value,
                    confidence=row.confidence,
                    source=row.source,
                    last_verified_at=row.last_verified_at,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]
            total_memories += len(rows)

        return ProjectSummaryResponse(
            project_id=str(project_id),
            categories=categories,
            total_memories=total_memories,
            stale_count=stale_count,
        )

    async def extract_facts_from_messages(
        self,
        messages: list[dict[str, str]],
        source: str = "ai_inferred",
    ) -> FactExtractionResponse:
        """Extract structured project facts from conversation messages.

        Uses Claude Haiku for cost-efficient fact extraction.

        Args:
            messages: Conversation messages to analyze.
            source: Source label for extracted facts.

        Returns:
            FactExtractionResponse with extracted facts.

        Raises:
            ProjectMemoryServiceError: If extraction fails.
        """
        await logger.ainfo(
            "fact_extraction_started",
            message_count=len(messages),
            source=source,
        )

        try:
            import anthropic

            settings = get_settings()
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

            # Format conversation for analysis
            conversation_text = "\n".join(
                f"[{msg.get('role', 'unknown')}]: {msg.get('content', '')}" for msg in messages
            )

            response = client.messages.create(
                model=settings.claude_simple_model,
                max_tokens=2048,
                system=_EXTRACTION_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Asagidaki konusmadan proje bilgilerini cikar:\n\n{conversation_text}"
                        ),
                    }
                ],
            )

            # Parse response
            response_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    response_text += block.text

            facts = self._parse_extraction_response(response_text, source)

            await logger.ainfo(
                "fact_extraction_completed",
                message_count=len(messages),
                facts_count=len(facts),
            )

            return FactExtractionResponse(
                extracted_facts=facts,
                total=len(facts),
            )
        except ProjectMemoryServiceError:
            raise
        except Exception as exc:
            await logger.aexception(
                "fact_extraction_failed",
                message_count=len(messages),
            )
            raise ProjectMemoryServiceError(
                f"Fact extraction basarisiz: {exc}",
                operation="extract_facts",
            ) from exc

    def _parse_extraction_response(
        self,
        response_text: str,
        source: str,
    ) -> list[ExtractedFact]:
        """Parse Claude response into structured facts.

        Args:
            response_text: Raw Claude response text.
            source: Source label for confidence defaults.

        Returns:
            List of ExtractedFact.
        """
        # Try to extract JSON from the response
        text = response_text.strip()

        # Handle markdown code blocks
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []

        facts: list[ExtractedFact] = []
        raw_facts = data.get("facts", [])
        if not isinstance(raw_facts, list):
            return []

        default_confidence = self._get_confidence_for_source(source)

        for item in raw_facts:
            if not isinstance(item, dict):
                continue

            category = str(item.get("category", "")).strip()
            key = str(item.get("key", "")).strip()
            value = item.get("value")

            if not category or not key or value is None:
                continue

            # Validate category
            if category not in VALID_CATEGORIES:
                continue

            # Truncate key to 100 chars
            key = key[:100]

            # Ensure value is a dict
            if not isinstance(value, dict):
                value = {"value": value}

            confidence = item.get("confidence", default_confidence)
            if not isinstance(confidence, (int, float)):
                confidence = default_confidence
            confidence = max(0.0, min(1.0, float(confidence)))

            facts.append(
                ExtractedFact(
                    category=category,
                    key=key,
                    value=value,
                    confidence=confidence,
                )
            )

        return facts

    async def extract_and_save_facts(
        self,
        repo: MemoryRepository,
        project_id: uuid.UUID,
        messages: list[dict[str, str]],
        source: str = "ai_inferred",
    ) -> FactExtractionResponse:
        """Extract facts from messages and save them to project memory.

        Combines extraction and UPSERT in a single operation.

        Args:
            repo: Memory repository instance.
            project_id: Project UUID.
            messages: Conversation messages to analyze.
            source: Source label.

        Returns:
            FactExtractionResponse with saved facts.
        """
        extraction = await self.extract_facts_from_messages(messages, source)

        for fact in extraction.extracted_facts:
            await repo.upsert(
                project_id=project_id,
                category=fact.category,
                key=fact.key,
                value=fact.value,
                confidence=fact.confidence,
                source=source,
            )

        await logger.ainfo(
            "facts_extracted_and_saved",
            project_id=str(project_id),
            facts_count=extraction.total,
        )

        return extraction

    async def cleanup_stale_entries(
        self,
        repo: MemoryRepository,
        project_id: uuid.UUID,
        days_threshold: int = _DEFAULT_STALE_DAYS,
    ) -> StaleCleanupResponse:
        """Delete stale project memory entries.

        Args:
            repo: Memory repository instance.
            project_id: Project UUID.
            days_threshold: Number of days to consider stale.

        Returns:
            StaleCleanupResponse with deletion count.
        """
        deleted_count = await repo.delete_stale_entries(project_id, days_threshold)

        await logger.ainfo(
            "stale_entries_cleaned",
            project_id=str(project_id),
            deleted_count=deleted_count,
            threshold_days=days_threshold,
        )

        return StaleCleanupResponse(
            deleted_count=deleted_count,
            threshold_days=days_threshold,
        )


# Module-level singleton
project_memory_service = ProjectMemoryService()
