# Task: Claude -p Execution'i Backend'den Agent'a Tasima

## Problem

Simdi backend (K8s pod icinde) kullanicinin mesajini alinca `claude -p` subprocess'ini **kendi icinde** calistiriyor. Ama:

1. K8s pod'unda proje dosyalari yok (`/Users/atakan/...` path'leri pod'da mevcut degil)
2. K8s pod'unda Claude Max subscription session'i yok
3. `FileNotFoundError` aliyor, fallback olarak Anthropic API'ye dusuyor, o da API key olmadigi icin basarisiz

## Hedef Mimari

```
iOS --> Backend (K8s) --> Agent (Mac'te) --> claude -p --> streaming sonuc
 ^                                                           |
 |___________________________________________________________|
                    (text delta streaming)
```

- **Backend**: Orchestrator rolu. Mesaji alir, hangi agent'a yonlendirecegini belirler, streaming sonuclari iOS'a iletir.
- **Agent**: Mac/Ubuntu uzerinde calisan daemon. `claude -p` subprocess'ini **kendi makinesinde** calistirabilir. Proje dosyalarina erisimi var.

## Mevcut Kod Analizi

### 1. Backend — Simdi `claude -p`'yi Nasil Calistiriyor

**Dosya: `apps/backend/app/orchestrator/claude_code_runner.py`**
- `ClaudeCodeRunner.run()` metodu (satir ~182-320)
- `claude -p "<prompt>" --output-format stream-json --model sonnet --max-turns 30 --verbose` komutu calistirir
- NDJSON stream parse eder: `message_start → content_block_delta* → result`
- 4 callback destekler:
  - `on_text_delta(delta, index)` — her token geldiginde
  - `on_tool_progress(event)` — tool kullanimi ilerleme bilgisi
  - `on_question(payload)` — kullaniciya soru sorma (AskUserQuestion)
  - `on_stream_end(full_text)` — stream tamamlandiginda

**Dosya: `apps/backend/app/services/orchestrator_service.py`**
- `process_with_claude_code()` metodu (satir 290-471)
- Proje local_path'ini DB'den cikarir
- Git context, memory context, recent conversation context olusturur
- `ClaudeCodeRunner.run()` cagirmak yerine **Agent'a dispatch etmeli**
- Session yonetimi: Redis'te `claude_session:{ws_session_id}:project:{project_id}` key'inde saklanir
- Session rotation: Her 40 mesajda bir yeni session baslatir

**Dosya: `apps/backend/app/api/routes/websocket.py`**
- `_process_with_orchestrator()` metodu (satir ~421-812)
- iOS'tan gelen TEXT/VOICE mesajlarini handler'a yonlendirir
- Streaming callback'leri tanimlar:
  - `_on_text_delta()` → iOS'a `CHAT_STREAM` mesaji gonderir
  - `_on_stream_end()` → iOS'a `CHAT_STREAM_END` gonderir
  - `_on_tool_progress()` → iOS'a `PROGRESS` gonderir
  - `_on_question()` → iOS'a `APPROVAL_REQUEST` gonderir, `APPROVAL_RESPONSE` bekler

### 2. Agent — Mevcut Task Execution Altyapisi

**Dosya: `apps/agent/agent/core/task_dispatcher.py`**
- `TaskDispatcher.dispatch(data)` metodu
- `task_execute` mesajini alir → runner secer → calistirir → `task_result` gonderir
- Mevcut runner'lar: `shell`, `docker`, `playwright`, `maestro`
- **SORUN: Request-response pattern, streaming yok**

**Dosya: `apps/agent/agent/core/connection.py`**
- `_listen_loop()` — gelen mesajlari dinler
- `_inject_skip_permissions()` — `claude` komutlarina `--dangerously-skip-permissions` ekler
- `send_message()` — backend'e mesaj gonderir

**Dosya: `apps/agent/agent/core/protocol.py`**
- Mesaj tipleri: `agent_register`, `heartbeat`, `task_execute`, `task_result`, `task_error`
- `TaskExecuteContent`: `task_id`, `runner`, `action`, `params`
- **Streaming mesaj tipi YOK**

**Dosya: `apps/agent/agent/runners/shell_runner.py`**
- `ShellRunner.execute()` — subprocess calistirir
- Guvenlik kontrolleri: blacklist, injection, whitelist
- Stdout/stderr yakalayip return eder (streaming degil)

### 3. Backend — Agent WebSocket Handler

**Dosya: `apps/backend/app/api/routes/agent_ws.py`**
- `agent_websocket_endpoint()` — Agent baglanti noktasi
- `task_result` ve `task_error` mesajlarini handler'a yonlendirir
- **Streaming mesaj tipi handle edilmiyor**

**Dosya: `apps/backend/app/services/task_manager_service.py`**
- `TaskManager.dispatch()` — `asyncio.Future` olusturur, `task_execute` gonderir, sonucu bekler
- Timeout'lar: shell=60s, docker=300s, playwright=120s, maestro=600s
- **Future-based bekleme, streaming callback destegi yok**

### 4. iOS Tarafinda Beklenen Mesaj Tipleri

iOS'un anladigi streaming mesajlari (degismeyecek):
- `CHAT_STREAM` → `{message_id, delta, index}` — token token metin
- `CHAT_STREAM_END` → `{message_id, full_text, model_used, tokens_used}` — son mesaj
- `PROGRESS` → `{task, step, total_steps, percentage, phase, steps_detail}` — ilerleme
- `TYPING_START` / `TYPING_END` — yazma gostergesi
- `APPROVAL_REQUEST` → kullaniciya soru
- `CODE_DIFF` → dosya degisiklikleri
- `SUGGESTION` → onerilen sorular

## Yapilmasi Gerekenler

### Adim 1: Agent Protocol'e Streaming Mesaj Tipleri Ekle

**Dosyalar:**
- `apps/agent/agent/core/protocol.py`
- `shared/api-contracts/agent-messages.json` (varsa)

Yeni mesaj tipleri:
```
claude_task_execute    (backend → agent)  — claude -p gorevi baslat
claude_stream_delta    (agent → backend)  — text delta (token)
claude_stream_progress (agent → backend)  — tool progress bilgisi
claude_stream_question (agent → backend)  — kullaniciya soru
claude_stream_end      (agent → backend)  — stream tamamlandi
claude_stream_error    (agent → backend)  — hata olustu
claude_question_answer (backend → agent)  — kullanici cevabi
```

`claude_task_execute` payload:
```json
{
  "task_id": "uuid",
  "prompt": "kullanici mesaji",
  "project_dir": "/Users/atakan/.../proje",
  "session_id": "onceki claude session id (resume icin)",
  "model": "sonnet",
  "max_turns": 30,
  "append_system_prompt": "context bilgisi"
}
```

`claude_stream_delta` payload:
```json
{
  "task_id": "uuid",
  "delta": "token metni",
  "index": 0
}
```

`claude_stream_end` payload:
```json
{
  "task_id": "uuid",
  "full_text": "tam cevap",
  "session_id": "claude session id (resume icin saklanacak)",
  "model_used": "claude-sonnet-4-6",
  "tokens_input": 1234,
  "tokens_output": 567
}
```

### Adim 2: Agent'a ClaudeCodeRunner Ekle

**Yeni dosya: `apps/agent/agent/runners/claude_runner.py`**

- Backend'deki `ClaudeCodeRunner` logigini Agent'a tasi
- `claude -p` subprocess'ini Agent makinesinde calistir
- NDJSON stream parse et
- Her delta'da `claude_stream_delta` mesaji gonder (WebSocket uzerinden backend'e)
- Tool progress'te `claude_stream_progress` gonder
- Soru geldiginde `claude_stream_question` gonder, `claude_question_answer` bekle
- Tamamlandiginda `claude_stream_end` gonder
- Hata durumunda `claude_stream_error` gonder

Dikkat edilecekler:
- `ANTHROPIC_API_KEY` env var'i OLMAMALI (Max subscription kullanilacak)
- `--dangerously-skip-permissions` flag'i eklenmeli
- `--output-format stream-json` kullanilmali
- Working directory olarak `project_dir` kullanilmali

### Adim 3: Agent Connection'a Streaming Handler Ekle

**Dosya: `apps/agent/agent/core/connection.py`**

- `_listen_loop()`'a `claude_task_execute` mesaj tipini ekle
- `claude_question_answer` mesajlarini aktif claude runner'a ilet
- Yeni `ClaudeRunner` instance'ini olustur ve task'i baslat

**Dosya: `apps/agent/agent/core/task_dispatcher.py`**

- `claude_task_execute` icin ozel dispatch logic (normal runner pattern'den farkli cunku streaming)

### Adim 4: Backend'de Agent'a Dispatch Et

**Dosya: `apps/backend/app/services/orchestrator_service.py`**

`process_with_claude_code()` metodunu degistir:
- `ClaudeCodeRunner.run()` yerine Agent'a `claude_task_execute` mesaji gonder
- Agent'tan gelen `claude_stream_delta` mesajlarini `on_text_delta` callback'ine yonlendir
- Agent'tan gelen `claude_stream_progress` → `on_tool_progress`
- Agent'tan gelen `claude_stream_question` → `on_question` → cevabi `claude_question_answer` ile agent'a gonder
- Agent'tan gelen `claude_stream_end` → `on_stream_end` + session kaydet
- Agent'tan gelen `claude_stream_error` → hata yonetimi

**Dosya: `apps/backend/app/api/routes/agent_ws.py`**

- Yeni streaming mesaj tiplerini handle et
- `claude_stream_delta`, `claude_stream_progress`, `claude_stream_question`, `claude_stream_end`, `claude_stream_error` icin handler'lar ekle
- Bu mesajlari ilgili iOS WebSocket session'ina yonlendir

**Dosya: `apps/backend/app/services/task_manager_service.py`**

- Streaming task'lar icin callback-based pattern ekle (Future yerine)
- Task ID ile iOS session/callback'leri eslestir

### Adim 5: Agent Secimi (Hangi Agent'a Gonderilecek?)

**Dosya: `apps/backend/app/api/routes/websocket.py`**

Mevcut durumda iOS'tan gelen mesajda `metadata.agentId` var. Bu agent'in WebSocket connection'ini bul ve o agent'a `claude_task_execute` gonder.

Eger `agentId` yoksa veya agent offline ise hata don.

### Adim 6: Backend'deki Eski ClaudeCodeRunner'i Temizle

Artik backend kendi icinde `claude -p` calistirmayacak. Simdi backend sadece bir proxy/orchestrator:

- `apps/backend/app/orchestrator/claude_code_runner.py` — Agent'a tasinacak, backend'den kaldirilabilir veya sadece fallback olarak kalabilir
- `process_with_claude_code()` icindeki `ClaudeCodeRunner` kullanimi kaldirilacak

## iOS Tarafinda Degisiklik

**GEREKLI DEGIL.** iOS zaten `CHAT_STREAM`, `PROGRESS`, `APPROVAL_REQUEST` mesajlarini handle ediyor. Backend bu mesajlari uretmeye devam edecek, sadece kaynak backend subprocess yerine Agent olacak.

## Agent Config Degisiklikleri

**Dosya: `apps/agent/agent/core/config.py`**

Yeni config field'lar:
```python
capability_claude: bool = Field(default=True, description="Claude Code destegi")
claude_model: str = Field(default="sonnet", description="Claude model (sonnet/opus/haiku)")
claude_max_turns: int = Field(default=30, ge=1, le=100, description="Claude max turns")
```

## Test Senaryolari

1. iOS'tan mesaj gonder → Backend agent'a dispatch eder → Agent `claude -p` calistirir → Streaming delta'lar iOS'a ulasir
2. Agent offline iken mesaj gonder → Hata mesaji doner
3. Claude -p tool kullaniyor → Progress mesajlari iOS'a ulasir
4. Claude kullaniciya soru soruyor → APPROVAL_REQUEST iOS'a ulasir → Kullanici cevaplar → Cevap agent'a iletilir
5. Session devam ettirme (--resume) calisiyor
6. Session rotation (40 mesajda bir) calisiyor
7. Agent baglantisi koparsa → Task timeout ile hata doner

## Oncelik Sirasi

1. **Agent protocol** — yeni mesaj tipleri (en az bagimlilik)
2. **Agent ClaudeRunner** — claude -p calistirma + streaming
3. **Backend agent_ws handler** — streaming mesajlari handle etme
4. **Backend orchestrator** — dispatch logigi degistirme
5. **Test** — end-to-end dogrulama
6. **Temizlik** — eski ClaudeCodeRunner kaldir

## Onemli Notlar

- `ANTHROPIC_API_KEY` hicbir yerde OLMAMALI. Sadece Claude Max subscription (`claude -p`) kullanilacak.
- Agent makinesinde `claude` CLI'in kurulu ve Max subscription ile auth edilmis olmasi gerekiyor.
- `--dangerously-skip-permissions` flag'i agent tarafinda ekleniyor (mevcut `_inject_skip_permissions` logigi zaten var).
- Backend pod'unda `claude` CLI'a gerek yok, kaldiriilabilir.
- iOS tarafinda HICBIR degisiklik gerekmez.
