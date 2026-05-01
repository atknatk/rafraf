# ADR-0004 — mem0, voice, multi-runner host agent feature'larını V2'ye ertele

**Status:** Accepted
**Date:** 2026-05-01
**Owner:** The Abi
**Related:** [`10_Production_Pivot_Spec.md`](../10_Production_Pivot_Spec.md) §5

## Context

RafRaf v0.1 vizyonu çok geniş kapsamlı bir "AI Project Supervisor": proje yönetim asistanı + sesli arayüz + 3-katmanlı bellek + multi-runner test infrastructure. Bu vizyonun teknik gerçekleştirilmesi:

- **Voice**: 3 iOS feature (VoiceInput, VoiceOutput, VoiceConversation, ~36 Swift dosyası) + Deepgram STT + OpenAI TTS dış servisleri
- **mem0**: 4 backend service (memory, conversation_memory, personal_memory, project_memory, ~1900 satır Python) + pgvector + mem0ai dependency + Postgres extension
- **Multi-runner host agent**: Docker, Maestro, Playwright, shell runners (`apps/agent/agent/runners/`) + scanner + testing/mobile + discovery (~25 Python module)
- **iOS scope explosion**: ScreenshotViewer, FileSharing, Pulse, Project, Tasks, Progress, Monitoring (~80 Swift)

Toplam dış servis: 13+ env var (Anthropic, Deepgram, OpenAI, GitHub, AWS×3, mem0, APNs×4). Setup adımı 30+. Kullanıcı **"aktiflestirememistim"** geri dönüşü = scope explosion sebebli.

V1 hedefi: useCoda paralel coding agent orchestration. Yukarıdakiler bu hedefe **ortogonal**.

## Decision

Aşağıdaki feature'lar **V1 scope dışı**. Kod silinir veya `_archive/`'a taşınır. V2 yol haritasında yeniden değerlendirilir.

**iOS — sil/ertele** (10 feature, ~116 Swift dosya):

| Feature | Aksiyon | Sebep |
|---|---|---|
| VoiceInput, VoiceOutput, VoiceConversation | sil → V2 | Deepgram + OpenAI TTS scope dışı |
| ScreenshotViewer | sil → V2 | Host agent ile bağlı |
| FileSharing | sil → V2 | V1 nice-to-have, kompleks UX |
| Pulse | sil → V2 | Reports dashboard, V2 feature |
| Project (sayfa) | sil → V2 | Standalone, Home + Chat yeterli V1'de |
| Tasks | merge to Agent → sil | Subagent UI içinde göster |
| Progress | merge to Agent → sil | Live Activity yeterli V1'de |
| Monitoring | sil → V2 | Backend observability yeterli |

**iOS — TUT** (8 feature): Auth, Onboarding, Home, Chat, Agent, Approval, Notifications, Settings.

**Backend — sil** (10 service, 13 route, 3 tool):

- mem0 servisleri × 4 (memory, conversation_memory, personal_memory, project_memory)
- voice servisleri (varsa)
- cost servisleri × 2 (cost_service, cost_alert_service)
- maestro_service (host agent ile bağlı)
- pulse_service
- analytics_service
- 10 ilgili route + 3 ilgili tool (memory_tool, cost_tool, host_agent_tool)
- 1 orchestrator (model_router — tek provider claude, router gereksiz)

**Backend — TUT**: auth, session, conversation, agent_registry (Faz 1'de bridge_registry'ye refactor), approval, audit, apns, live_activity_push, notification, orchestrator, git_context, git_diff, github, project, proactive_notification, backup, s3, claude_stream_manager.

**apps/agent/** (Python host daemon):

- `apps/agent/` → `apps/_archive/agent-python-v0.1/` (referans olarak korunur, [ADR-0003](0003-rewrite-host-agent-as-go-bridge.md) port'u sırasında claude_runner.py'ye bakılacak)
- Yerine `apps/rafraf-bridge/` Go binary, **sadece claude bridge rolü** — Docker/Maestro/Playwright runners V1'de YOK.

**Dış servis dependency'leri**:

| Servis | V1 | Sebep |
|---|---|---|
| Anthropic Claude (subscription) | ✅ ZORUNLU | Tek AI provider |
| PostgreSQL 16 | ✅ ZORUNLU | Backend storage |
| Redis 7 | ✅ ZORUNLU | Pubsub + cache |
| AWS S3 | ✅ V1 (backup) | RDS dump backup, attachment storage |
| Apple APNs | ✅ ZORUNLU | Live Activity + push |
| GitHub PAT | ⚠️ OPSİYONEL | PR tracking; V1 launch blocker değil |
| ANTHROPIC_API_KEY | ⚠️ OPSİYONEL | Sadece fallback (V1'de kapalı default) |
| **Deepgram STT** | ❌ V2 | Voice |
| **OpenAI TTS** | ❌ V2 | Voice |
| **AWS Bedrock** | ❌ V1 | USE_BEDROCK kaldırıldı |
| **mem0** | ❌ V2 | Memory system V2 |
| **pgvector** | ❌ V2 | mem0 ile birlikte |

## Consequences

**Pozitif:**
- env var sayısı 23 → 12 (~%50 azalma); setup adımları drastically sadeleşir.
- iOS Swift dosya sayısı 296 → ~180 (%40 azalma); build süresi düşer, test surface küçülür.
- Backend Python LOC ~5700+ azalır (10 service + 13 route + 3 tool + 1 orchestrator).
- "AI Project Supervisor" vizyonundan "useCoda paralel agent orchestrator" hedefine **odaklı** scope.
- Faz 0 (cleanup) 1 hafta'da tamamlanabilir; aksi takdirde scope reduction tek başına 3-4 hafta'lık iş olurdu.

**Negatif:**
- Voice features kullanıcının ilgi gösterdiği bir özellikti; V2 bekletme süresinde "kayıp" his.
- mem0 (3-katmanlı bellek) RafRaf'ın diferansiyatörlerinden biriydi; V1'de basit Postgres conversation history ile yetinmek deneyim eksikliği yaratabilir.
- Multi-runner (Maestro/Playwright/Docker) RafRaf'ın orijinal vizyonuna özgüydü; V2'de yeniden değerlendirilirken Anthropic Claude Code'un kendi Bash/Edit/MCP tool'larıyla bu ihtiyaç zaten karşılanıyor olabilir.
- iOS 80+ Swift dosya silindi; bazı View'larda useful kod var (RFGlassBar style, Live Activity templates), bunlar Agent feature'a merge edilmek zorunda — manuel inceleme.

**V2 entry criteria** (yeniden ele alınması için):

- V1 production'da stabil ve aktif kullanılıyor (en az 1 ay)
- Kullanıcı geri dönüşü pozitif: hangi V0.1 feature'ı eksikliği hissediliyor?
- Voice → user testing'de ortaya çıkarsa Deepgram alternatif (Apple Speech API native?) düşünülür.
- mem0 → iOS Chat ekranında basit "previous sessions" lookup yetiyor mu, yoksa structured memory gerekiyor mu?

## Alternatives considered

- **A) Tüm v0.1 vizyonu V1'e sığdır**: 4-5 ay süre, 13 dış servis bağımlılığı, kullanıcının V1'i aktiflestirme şansı düşük (zaten v0.1'de oldu). **Reddedildi** — pragmatik değil.
- **B) V1'i sadece iOS app**, backend'e dokunma: backend monolith zaten var, ekleme yapamaz, mimari evrim engellenir. **Reddedildi**.
- **C) v0.1'i tamamen at, useCoda sıfırdan yaz**: 800 MB+ kod ziyan, iOS Clean Arch + RF* design + WebSocket protocol + Auth + Live Activity + TestFlight CI hepsi yeniden yazılır (2-3 ay extra). **Reddedildi** — yeniden ele alındı, [`10_Production_Pivot_Spec.md`](../10_Production_Pivot_Spec.md) "C → A" pivot'una karar verildi.
- **D) (Seçildi)** Scope reduction + Bridge port: v0.1'in iyi parçalarını koru (iOS Clean Arch, backend skeleton, WS protocol, Auth, Live Activity, TestFlight CI), eskiyenleri sil/ertele.

## Migration notes

- Faz 0 task'ları: T0.3-T0.11 ([`12_Action_Plan_Tasks.md`](../12_Action_Plan_Tasks.md)).
- Voice features sil edilmeden önce iOS app'in Voice DI registration'ları (Factory) ayrıca temizlenmeli.
- mem0 docker volume + pgvector init script de cleanup'a dahil.
- Doc'lardan ARCHIVED notları: 03_AI_Agent_Tool_Layer_Specification, 05_Memory_System_Specification, 08_Host_Agent_Specification.
