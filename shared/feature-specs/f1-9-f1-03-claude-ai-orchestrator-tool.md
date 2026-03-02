# Feature: Claude AI Orchestrator + Tool-Calling Loop

**Issue**: #9
**Faz**: F1
**Katmanlar**: backend
**Pipeline**: full
**Tarih**: 2026-03-02

## Ozet

Claude Agent SDK ile AI reasoning ve tool-calling loop implementasyonu. Kullanicidan gelen mesajlari Claude API'a iletip, tool call'lari yonetip, sonuclari iOS istemcisine donen ana orkestrator modulu. Bu modul, backend'in beyin katmanini olusturur ve tum AI islemlerinin merkezidir.

## Degisecek Dosyalar

### Backend (`apps/backend/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/orchestrator/__init__.py` | CREATE | Orchestrator package init |
| `app/orchestrator/agent.py` | CREATE | Claude Agent SDK entegrasyonu, tool-calling loop |
| `app/orchestrator/tool_registry.py` | CREATE | Tool tanimlari ve dispatch mekanizmasi |
| `app/orchestrator/model_router.py` | CREATE | Akilli model secimi (Haiku/Sonnet) |
| `app/orchestrator/prompt_builder.py` | CREATE | System prompt ve context olusturma |
| `app/schemas/orchestrator.py` | CREATE | Orchestrator Pydantic request/response modelleri |
| `app/services/orchestrator_service.py` | CREATE | Orchestrator business logic servisi |
| `app/core/config.py` | MODIFY | Claude API ayarlarini ekle |
| `app/api/routes/websocket.py` | MODIFY | Text/voice handler'lari orchestrator'a yonlendir |
| `app/schemas/messages.py` | MODIFY | Yeni mesaj tiplerini ekle (action_result, question, status, approval_response) |

## API Endpoints

### REST
Bu feature yeni REST endpoint eklemez. Orchestrator WebSocket uzerinden calisir.

### WebSocket Messages
| Direction | Type | Payload | Aciklama |
|-----------|------|---------|----------|
| client->server | `text` | `{ "content": "..." }` | Metin mesaji (mevcut, orchestrator'a yonlendirilecek) |
| client->server | `voice` | `{ "content": "..." }` | Ses mesaji (mevcut, orchestrator'a yonlendirilecek) |
| client->server | `approval_response` | `{ "approval_id": "...", "decision": "approved/rejected" }` | Onay cevabi |
| server->client | `text` | `{ "text": "..." }` | AI metin cevabi (streaming partial) |
| server->client | `progress` | `{ "task": "...", "step": N, "total_steps": N }` | Islem ilerleme bildirimi |
| server->client | `action_result` | `{ "tool": "...", "action": "...", "success": bool }` | Tool sonucu |
| server->client | `question` | `{ "approval_id": "...", "question": "...", "options": [...] }` | Onay sorusu |
| server->client | `error` | `{ "error_code": "...", "message": "..." }` | Hata mesaji |

## Data Model

### Pydantic Models

```python
class ToolDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    description: str
    input_schema: dict[str, object]
    requires_approval: bool = False
    approval_category: str | None = None

class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str
    input: dict[str, object]

class ToolResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool_use_id: str
    content: str
    is_error: bool = False

class OrchestratorRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    session_id: str
    user_id: str
    message: str
    project_id: str | None = None

class OrchestratorResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    session_id: str
    response_text: str
    model_used: str
    tokens_input: int
    tokens_output: int
    tool_calls_count: int

class ModelRouterResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    model: str
    reason: str
```

## Business Rules

1. Tool-calling loop maksimum 10 iterasyonda sonlanmali (sonsuz dongu korunmasi)
2. Model secimi mesaj icerigine gore otomatik yapilmali (basit isler Haiku, karmasik isler Sonnet)
3. Onay gerektiren tool call'larda kullaniciya soru gonderilmeli ve cevap beklenilmeli (timeout: 5 dakika)
4. Tool registry'ye tool ekleme/cikarma dinamik olmali
5. Streaming partial response destegi (tool calisirken ilerleme bildirimi)
6. Claude API hata durumlarinda exponential backoff ile retry (429, 500, 529)
7. Conversation context her mesajda korunmali (session bazli)
8. System prompt proje bazli dinamik context icermeli

## Test Requirements

### Backend
- [ ] Unit test: model_router - basit ve karmasik mesaj secimi
- [ ] Unit test: tool_registry - tool ekleme, cikarma, arama
- [ ] Unit test: prompt_builder - system prompt olusturma
- [ ] Unit test: orchestrator_service - tool-calling loop mantigi
- [ ] Integration test: orchestrator ile WebSocket entegrasyonu
- [ ] Integration test: Claude API mock ile end-to-end tool-calling akisi
- [ ] Edge case: Max iteration siniri (10 iterasyon)
- [ ] Edge case: Claude API timeout/rate limit

## Acceptance Criteria

- [ ] Claude Agent SDK entegrasyonu tamamlandi
- [ ] Tool-calling loop calisiyor (tool cagir -> sonuc al -> devam et)
- [ ] System prompt yonetimi (proje bazli dinamik context)
- [ ] Streaming response (partial mesajlar iOS'a WebSocket ile)
- [ ] Tool registry sistemi (tool ekleme/cikarma)
- [ ] Error handling (API timeout, rate limit, max iteration)
- [ ] Conversation context yonetimi (session bazli)
- [ ] Model router (Haiku/Sonnet secimi)
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
