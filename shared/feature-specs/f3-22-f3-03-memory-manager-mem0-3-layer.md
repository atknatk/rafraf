# Feature: Memory Manager (mem0 + 3-Layer)

**Issue**: #22
**Faz**: F3
**Katmanlar**: backend
**Pipeline**: full
**Tarih**: 2026-03-02

## Ozet

mem0 ile 3-katmanli hafiza sistemi. Conversation (kisa sureli, Redis), Project (orta sureli, PostgreSQL) ve Personal (uzun sureli, mem0+pgvector) hafiza yonetimi. AI her konusmada kullanicinin tercihlerini, proje durumunu ve gecmis bilgileri hatirlar. Memory manager, backend icinde cloud tool olarak calisir (host agent gerektirmez).

## Degisecek Dosyalar

### Backend (`apps/backend/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/models/memory.py` | CREATE | ProjectMemory SQLAlchemy modeli |
| `app/schemas/memory.py` | CREATE | Memory Pydantic request/response semalari |
| `app/repositories/memory_repository.py` | CREATE | ProjectMemory DB erisim katmani |
| `app/services/memory_service.py` | CREATE | 3-katmanli hafiza business logic |
| `app/tools/memory_tool.py` | CREATE | Claude tool tanimlari (memory_manager) |
| `app/api/routes/memory.py` | CREATE | REST API endpoint'leri (admin/debug) |
| `app/core/config.py` | MODIFY | mem0 konfigurasyonu eklenmesi |
| `app/core/redis.py` | CREATE | Redis client wrapper (conversation memory) |
| `app/main.py` | MODIFY | Memory router ve lifespan eklenmesi |
| `app/models/__init__.py` | MODIFY | ProjectMemory import |
| `app/schemas/__init__.py` | MODIFY | Memory semalari import |
| `app/tools/__init__.py` | MODIFY | MemoryTool import |

## API Endpoints

### REST (Admin/Debug)
| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| GET | `/api/v1/memory/project/{project_id}` | Query: category?, key? | `ProjectMemoryListResponse` | Proje hafizasini listele |
| POST | `/api/v1/memory/project/{project_id}` | `ProjectMemoryCreateRequest` | `ProjectMemoryResponse` | Proje hafizasi ekle/guncelle |
| DELETE | `/api/v1/memory/project/{project_id}/{memory_id}` | - | `204 No Content` | Proje hafizasi sil |
| GET | `/api/v1/memory/personal/{user_id}` | Query: query?, limit? | `PersonalMemoryListResponse` | Kisisel hafiza ara |
| DELETE | `/api/v1/memory/personal/{user_id}/{memory_id}` | - | `204 No Content` | Kisisel hafiza sil |
| GET | `/api/v1/memory/context/{user_id}` | Query: message, project_id? | `MemoryContextResponse` | Mesaj icin tam context olustur |

### WebSocket Messages (Claude Tool)
| Direction | Type | Payload | Aciklama |
|-----------|------|---------|----------|
| internal | `tool.memory_manager` | `{action, params}` | Claude tarafindan cagrilir (cloud tool) |

## Data Model

### PostgreSQL

```sql
CREATE TABLE project_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    category VARCHAR(50) NOT NULL,
    key VARCHAR(100) NOT NULL,
    value JSONB NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    source VARCHAR(50) NOT NULL DEFAULT 'ai_inferred',
    last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(project_id, category, key)
);

CREATE INDEX idx_project_memory_project_id ON project_memory(project_id);
CREATE INDEX idx_project_memory_category ON project_memory(project_id, category);
```

### Pydantic Models

```python
class ProjectMemoryEntity(BaseModel):
    """Immutable project memory domain entity."""
    model_config = ConfigDict(frozen=True)

    id: UUID
    project_id: UUID
    category: str
    key: str
    value: dict[str, object]
    confidence: float
    source: str
    last_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MemoryContext(BaseModel):
    """Memory context for Claude API calls."""
    model_config = ConfigDict(frozen=True)

    personal_memories: list[str]
    project_summary: dict[str, object]
    recent_actions: list[dict[str, object]]
    conversation_summary: str | None
    token_count: int


class ProjectMemoryCreateRequest(BaseModel):
    """Request to create/update project memory."""
    category: str
    key: str
    value: dict[str, object]
    confidence: float = 1.0
    source: str = "user_stated"


class ProjectMemoryResponse(BaseModel):
    """Single project memory response."""
    id: UUID
    project_id: UUID
    category: str
    key: str
    value: dict[str, object]
    confidence: float
    source: str
    last_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectMemoryListResponse(BaseModel):
    """List of project memories."""
    items: list[ProjectMemoryResponse]
    total: int


class PersonalMemoryItem(BaseModel):
    """Single personal memory item from mem0."""
    model_config = ConfigDict(frozen=True)

    id: str
    memory: str
    score: float | None
    metadata: dict[str, object] | None


class PersonalMemoryListResponse(BaseModel):
    """List of personal memories."""
    items: list[PersonalMemoryItem]
    total: int


class MemoryContextResponse(BaseModel):
    """Full memory context response."""
    personal_memories: list[str]
    project_summary: dict[str, object]
    conversation_summary: str | None
    token_count: int
```

## Business Rules

1. **Conversation Memory (Redis)**: Oturum bazli, TTL = session suresi. Oturum bitince ozetlenir ve mem0'ya kaydedilir.
2. **Project Memory (PostgreSQL)**: Proje bazli structured bilgi. UPSERT semantigi (project_id + category + key unique). `last_verified_at` 30 gunden eski kayitlar "stale" isaretlenir.
3. **Personal Memory (mem0+pgvector)**: Kullanici bazli semantic search. mem0 otomatik fact extraction yapar. Similarity threshold: 0.60 ustu dahil edilir.
4. **Context Building**: Her mesaj oncesi get_context_for_message cagrilir. Personal memories + project summary + conversation summary birlestirilir. Max token budget: personal=1500, project=1000, conversation_summary=500.
5. **Source Tracking**: Her hafiza kaydinin source'u takip edilir: `user_stated`, `ai_inferred`, `tool_result`.
6. **Confidence Scoring**: 0.0-1.0 arasi. user_stated=1.0, tool_result=0.9, ai_inferred=0.7 default.
7. **Memory Tool**: Claude tool olarak `memory_manager` tanimlanir. Cloud tool kategorisinde (EKS uzerinde calisir).

## Test Requirements

### Backend
- [ ] Unit test: MemoryService.get_context_for_message — personal + project + conversation birlesimi
- [ ] Unit test: MemoryService.save_conversation_facts — fact extraction
- [ ] Unit test: MemoryService.update_project_memory — UPSERT semantigi
- [ ] Unit test: MemoryService.search_memories — semantic search
- [ ] Unit test: MemoryService.get_project_summary — proje ozeti
- [ ] Unit test: ProjectMemoryRepository CRUD islemleri
- [ ] Unit test: Redis conversation cache set/get/delete
- [ ] Unit test: MemoryTool.execute — tum action'lar
- [ ] Integration test: mem0 + pgvector entegrasyonu
- [ ] Integration test: REST API endpoint'leri (CRUD)
- [ ] Integration test: Conversation ozet -> mem0 kayit dongusu
- [ ] Integration test: Tool sonucu -> project memory guncelleme

## Acceptance Criteria

- [ ] mem0 entegrasyonu calisiyor (add, search, update, delete)
- [ ] 3 katman: conversation (Redis), project (PostgreSQL), personal (mem0+pgvector)
- [ ] Hafiza kaydetme/sorgulama API calisiyor
- [ ] Otomatik fact extraction (conversation'dan mem0'ya)
- [ ] Hafiza arama (semantic search, pgvector)
- [ ] Tool tanimlari (Claude tool schema — memory_manager)
- [ ] REST API endpoint'leri (admin/debug)
- [ ] Context builder token limiti uyumu
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
