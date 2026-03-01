# RafRaf — Memory System Specification

**Document 5/8** | Version 1.0 | March 2026

---

## 1. Genel Bakis

Memory sistemi, RafRaf'i "seni taniyan" bir asistana donusturen temel bilesendir. Kullanicinin tercihlerini, projelerin durumunu ve gecmis konusmalardaki onemli bilgileri hatirlayarak, her yeni konusmanin sifirdan baslamasini onler.

### 1.1 Neden mem0?

| Ozellik | mem0 | Custom (pgvector) | Zep | Letta |
|---------|------|-------------------|-----|-------|
| Otomatik fact extraction | ✅ | ❌ (manual) | ✅ | ✅ |
| Acik kaynak | ✅ | N/A | ✅ | ✅ |
| Python SDK | ✅ | N/A | ✅ | ✅ |
| Self-hosted | ✅ | ✅ | ✅ | ✅ |
| Setup kolayligi | Kolay | Orta | Orta | Zor |
| PostgreSQL destegi | ✅ (pgvector) | Native | ❌ | ❌ |
| Ek framework bagimiligi | Yok | Yok | Yok | Kendi framework'u |

**Secim: mem0** — Otomatik fact extraction, kolay setup, PostgreSQL uyumu ve bagimsiz calisabilme. Kendi agent framework'unu dayatmayan tek secenek.

---

## 2. Memory Katmanlari

Uc katmanli hafiza sistemi:

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  Katman 1: Kisa Sureli (Conversation Memory)        │
│  ─────────────────────────────────────────────      │
│  • Mevcut konusmanin tam gecmisi                    │
│  • Claude API conversation history                  │
│  • Omur: Oturum suresi (oturum bitince ozetlenir)   │
│  • Depolama: In-memory (Redis)                      │
│                                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Katman 2: Orta Sureli (Project Memory)             │
│  ─────────────────────────────────────────────      │
│  • Proje bazli bilgiler                             │
│  • Issue durumu, son deploy, bilinen buglar          │
│  • Omur: Surekli (guncellenir)                      │
│  • Depolama: PostgreSQL (structured)                │
│                                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Katman 3: Uzun Sureli (Personal Memory / mem0)     │
│  ─────────────────────────────────────────────      │
│  • Kullanici tercihleri ve aliskanliklar            │
│  • Gecmis kararlar ve sebebleri                     │
│  • Proje arasi bilgiler                             │
│  • Omur: Kalici                                     │
│  • Depolama: mem0 + pgvector                        │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 3. Katman 1: Conversation Memory (Kisa Sureli)

### 3.1 Amac

Mevcut konusmadaki context'i korumak. "Az once bahsettigim proje" veya "onu da yap" gibi referanslari anlamak icin.

### 3.2 Uygulama

Claude API'nin conversation history mekanizmasi kullanilir. Her mesaj `messages` dizisine eklenir.

```json
{
  "messages": [
    { "role": "user", "content": "Proje X'in durumunu kontrol et" },
    { "role": "assistant", "content": "...", "tool_calls": [...] },
    { "role": "tool", "tool_call_id": "...", "content": "..." },
    { "role": "assistant", "content": "Proje X: 3/5 issue tamamlandi..." },
    { "role": "user", "content": "Docker loglarini goster" },
    { "role": "assistant", "content": "..." }
  ]
}
```

### 3.3 Token Yonetimi

Conversation history cok uzarsa token limiti asilir. Strateji:

- **Max conversation tokens:** 50,000 (input)
- **Esik asildiginda:** Eski mesajlar ozetlenir
- **Ozet stratejisi:** Claude'a "bu konusmayi 500 token'da ozetle" denilir, ozet yeni mesajlarin basina eklenir
- **Tool sonuclari:** Uzun tool output'lari kisaltilir (max 2000 token/tool)

### 3.4 Oturum Sonu

Oturum bittiginde (WebSocket kapatildiginda veya 30 dakika inaktivite):
1. Konusmanin ozeti cikarilir
2. Onemli bilgiler mem0'ya kaydedilir
3. Audit log'a session ozeti yazilir
4. Redis'teki conversation cache temizlenir

---

## 4. Katman 2: Project Memory (Orta Sureli)

### 4.1 Amac

Her proje hakkindaki guncel bilgileri yapisal olarak saklamak. AI her konusmada projenin son durumunu bilsin.

### 4.2 Veri Yapisi

PostgreSQL'de `project_memory` tablosu:

```sql
CREATE TABLE project_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    category VARCHAR(50) NOT NULL,
    key VARCHAR(100) NOT NULL,
    value JSONB NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    source VARCHAR(50),           -- "user_stated", "ai_inferred", "tool_result"
    last_verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, category, key)
);
```

### 4.3 Kategori ve Icerikler

**tech_stack — Teknoloji bilgileri:**
```json
{
  "category": "tech_stack",
  "key": "frontend",
  "value": {
    "framework": "Next.js",
    "version": "14.2",
    "language": "TypeScript",
    "ui_library": "Tailwind CSS",
    "state_management": "Zustand"
  }
}
```

**known_issues — Bilinen sorunlar:**
```json
{
  "category": "known_issues",
  "key": "login_redirect_bug",
  "value": {
    "description": "Login sonrasi redirect bazen calismiyor",
    "github_issue": "#42",
    "status": "in_progress",
    "assignee": "ai-agent-1",
    "notes": "OAuth callback URL sorunu olabilir"
  }
}
```

**deployment — Deploy bilgileri:**
```json
{
  "category": "deployment",
  "key": "last_production_deploy",
  "value": {
    "date": "2026-02-28T14:30:00Z",
    "version": "v2.3.1",
    "commit": "abc123",
    "deployed_by": "github-actions",
    "status": "success",
    "notes": "2 bug fix, 1 feature"
  }
}
```

**architecture_decisions — Mimari kararlar:**
```json
{
  "category": "architecture_decisions",
  "key": "auth_approach",
  "value": {
    "decision": "JWT with refresh tokens",
    "date": "2026-01-15",
    "reason": "Stateless, mobile uyumlu, session yonetimi gerektirmez",
    "alternatives_considered": ["session-based", "OAuth only"]
  }
}
```

### 4.4 Guncelleme Mekanizmasi

Project memory su durumlarda guncellenir:
- **Tool sonucu:** Docker health check, GitHub issue listesi, test sonuclari
- **Kullanici ifadesi:** "Proje X'te artik MongoDB kullaniyoruz"
- **AI cikarimi:** Kod analizinden tech stack degisikligi tespit edildi

Her guncelleme `source` alani ile isaretlenir (user_stated, ai_inferred, tool_result).

---

## 5. Katman 3: Personal Memory (Uzun Sureli / mem0)

### 5.1 Amac

Kullanicinin kisisel tercihlerini, calisma tarzini ve gecmis kararlari saklamak. AI kullaniciyi "tanisin."

### 5.2 mem0 Konfigurasyonu

```python
from mem0 import Memory

config = {
    "vector_store": {
        "provider": "pgvector",
        "config": {
            "connection_string": "postgresql://user:pass@postgres:5432/supervisor",
            "collection_name": "memories",
            "embedding_model_dims": 1536
        }
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "model": "text-embedding-3-small",
            "api_key": "sk-..."
        }
    },
    "llm": {
        "provider": "anthropic",
        "config": {
            "model": "claude-haiku-4-5-20251001",
            "api_key": "sk-ant-..."
        }
    }
}

memory = Memory.from_config(config)
```

### 5.3 Memory Islemleri

**Hafiza Ekleme (Her konusma sonunda):**
```python
# Konusma metninden otomatik fact extraction
memory.add(
    messages=conversation_messages,
    user_id="atakan",
    metadata={
        "session_id": "session_uuid",
        "projects_discussed": ["project-x", "project-y"],
        "timestamp": "2026-03-01T10:30:00Z"
    }
)
```

**Hafiza Sorgulama (Her konusma basinda):**
```python
# Kullanici mesajina gore ilgili hafizalari cek
relevant_memories = memory.search(
    query=user_message,
    user_id="atakan",
    limit=10
)

# Ornek sonuc:
# [
#   {"memory": "Atakan kisa cevap tercih eder", "score": 0.92},
#   {"memory": "Proje X'te Next.js 14 kullaniliyor", "score": 0.87},
#   {"memory": "Docker loglarini detayli istiyor", "score": 0.85},
#   {"memory": "Sabahları ilk is proje durumunu sorar", "score": 0.78}
# ]
```

**Hafiza Guncelleme:**
```python
# Mevcut bir hafizayi guncelle
memory.update(
    memory_id="mem_uuid",
    data="Proje X artik Next.js 15 kullaniyor (14'ten upgrade edildi)"
)
```

**Hafiza Silme:**
```python
# Yanlis veya eski hafizayi sil
memory.delete(memory_id="mem_uuid")
```

### 5.4 Otomatik Fact Extraction Ornekleri

mem0, konusmalardan su tur bilgileri otomatik cikarir:

| Konusmadaki Ifade | Cikarilan Hafiza |
|-------------------|------------------|
| "Bana kisa cevap ver" | "Atakan kisa ve oze cevaplar tercih eder" |
| "Proje X'te MongoDB'ye gectik" | "Proje X'te veritabani MongoDB olarak degistirildi" |
| "Her zaman test sonuclarini detayli goster" | "Atakan test sonuclarini detayli gormek istiyor" |
| "Docker loglarinda son 200 satir yeterli" | "Docker log kontrolunde 200 satir tercih ediliyor" |
| "Sabah ilk is proje durumlarini kontrol et" | "Atakan sabahları proje durumu kontrolu ile baslar" |
| "Bu issue'yu kapama, henuz bitmedi" | "Issue #42 henuz tamamlanmadi, kapatilmamali" |

### 5.5 Context Window'a Ekleme

Her Claude API cagrisinda, ilgili hafizalar system prompt'a eklenir:

```
# Kullanici Hafizasi
Asagidaki bilgiler kullanici hakkinda daha onceki konusmalardan ogrenilmistir:
- Atakan kisa ve oze cevaplar tercih eder
- Sabahları proje durumu kontrolu ile baslar
- Docker loglarda 200 satir tercih ediyor
- Test sonuclarini detayli gormek istiyor
- Proje X'te Next.js 15, PostgreSQL kullaniliyor
- Proje Y'de FastAPI, MongoDB kullaniliyor

# Proje Durumu (Project Memory)
Proje X: 5 acik issue, Docker calisiyor, son deploy 2 gun once
Proje Y: 8 acik issue, Docker durdurulmus, son deploy 1 hafta once
```

---

## 6. Memory Lifecycle (Hafiza Yasam Dongusu)

### 6.1 Ekleme Zamanlari

| Olay | Katman | Islem |
|------|--------|-------|
| Kullanici mesaj gonderdi | Conversation | Mesaj history'ye eklenir |
| Tool calistirildi | Project | Sonuca gore proje hafizasi guncellenir |
| Oturum bitti | Personal (mem0) | Konusma ozetinden fact extraction |
| Kullanici acikca belirtti | Personal (mem0) + Project | Aninda kaydedilir |
| Periyodik kontrol | Project | GitHub issues, Docker status guncellenir |

### 6.2 Guncelleme Zamanlari

- **Project Memory:** Her tool calistirmadan sonra otomatik
- **Personal Memory:** Celiskili bilgi tespit edildiginde (eski → yeni)
- **Conversation Memory:** Her mesajda, ozetleme gerektiginde

### 6.3 Silme / Eskime

- **Conversation Memory:** Oturum sonunda silinir (ozet kalir)
- **Project Memory:** `last_verified_at` 30 gunden eski ise "stale" isaretlenir
- **Personal Memory:** Kullanici istegi ile veya celiskili bilgi durumunda
- **Otomatik temizlik:** Haftada bir, dusuk confidence'li ve 90 gunden eski hafizalar gozden gecirilir

---

## 7. Memory API (Backend Icin)

### 7.1 Internal API Endpoints

```python
# Memory service - backend icinde kullanilir

class MemoryService:

    async def get_context_for_message(
        self,
        user_id: str,
        message: str,
        project_id: str = None
    ) -> MemoryContext:
        """Her mesaj oncesi cagrilir. Ilgili tum hafizalari toplar."""

    async def save_conversation_facts(
        self,
        user_id: str,
        session_id: str,
        messages: list
    ) -> list[str]:
        """Oturum sonunda konusmadan fact extraction yapar."""

    async def update_project_memory(
        self,
        project_id: str,
        category: str,
        key: str,
        value: dict,
        source: str
    ) -> None:
        """Tool sonuclarina gore proje hafizasini gunceller."""

    async def search_memories(
        self,
        user_id: str,
        query: str,
        limit: int = 10
    ) -> list[Memory]:
        """Ilgili kisisel hafizalari arar."""

    async def get_project_summary(
        self,
        project_id: str
    ) -> dict:
        """Projenin tum hafiza ozetini dondurur."""
```

### 7.2 MemoryContext Nesnesi

```python
@dataclass
class MemoryContext:
    personal_memories: list[str]    # mem0'dan gelen ilgili hafizalar
    project_summary: dict           # Proje hafiza ozeti
    recent_actions: list[dict]      # Son 5 islem (audit log)
    conversation_summary: str       # Onceki oturum ozeti (varsa)
    token_count: int                # Toplam context token sayisi
```

---

## 8. Embedding ve Vector Search

### 8.1 Embedding Modeli

| Model | Boyut | Maliyet | Performans |
|-------|-------|---------|------------|
| text-embedding-3-small (OpenAI) | 1536 | $0.02/1M token | Iyi |
| text-embedding-3-large (OpenAI) | 3072 | $0.13/1M token | Cok iyi |

**Secim: text-embedding-3-small** — Maliyet/performans dengesi. Hafiza sorgusu icin yeterli kalite.

### 8.2 pgvector Konfigurasyonu

```sql
-- pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- mem0 tablosu (mem0 tarafindan otomatik olusturulur)
-- Ama indeks optimize etmek icin:
CREATE INDEX ON memories USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

### 8.3 Similarity Search

mem0 arka planda cosine similarity kullanir. Threshold degerleri:

| Score | Anlam | Kullanim |
|-------|-------|----------|
| > 0.90 | Cok yuksek ilgi | Kesinlikle ekle |
| 0.75 - 0.90 | Yuksek ilgi | Muhtemelen ekle |
| 0.60 - 0.75 | Orta ilgi | Yer varsa ekle |
| < 0.60 | Dusuk ilgi | Ekleme |

---

## 9. Memory Token Butcesi

Her Claude API cagrisinda context window'un ne kadari hafizaya ayrilacagi:

| Icerik | Max Token | Oncelik |
|--------|-----------|---------|
| System prompt | 2,000 | Sabit |
| Tool tanimlari | 3,000 | Sabit |
| Personal memories (mem0) | 1,500 | Yuksek |
| Project summary | 1,000 | Yuksek |
| Recent actions | 500 | Orta |
| Conversation history | 40,000 | Degisken |
| **Toplam max input** | **~48,000** | |

Conversation history, diger sabit iceriklerden kalan alani kullanir. Cok uzun konusmalarda eski mesajlar ozetlenir.

---

## 10. Test Stratejisi

### 10.1 Unit Tests

- mem0 fact extraction dogruluğu (verilen konusma → beklenen fact'ler)
- Project memory CRUD islemleri
- Context builder token limiti uyumu
- Similarity search threshold dogrulugu

### 10.2 Integration Tests

- mem0 + PostgreSQL + pgvector entegrasyonu
- Conversation ozet → mem0 kayit dongusu
- Tool sonucu → project memory guncelleme dongusu
- Memory context → Claude API cagri formati

### 10.3 Kalite Metrikleri

| Metrik | Hedef |
|--------|-------|
| Fact extraction dogruluğu | > %85 |
| Ilgili hafiza getirme (recall) | > %80 |
| Yanlis pozitif orani | < %15 |
| Memory query latency | < 200ms |
| Context build suresi | < 500ms |

---

*Bu dokuman RafRaf serisinin 5/8 numarali dokumanidir.*
*Onceki: 04_iOS_App_Specification.md*
*Sonraki: 06_Testing_Strategy.md*
