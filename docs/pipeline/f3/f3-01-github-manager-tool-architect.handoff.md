# Architect Handoff: GitHub Manager Tool

**Issue**: #20
**Faz**: F3
**Tarih**: 2026-03-02
**Sonraki Agent**: developer

## Ozet

GitHub API islemlerini Claude tool olarak sunan cloud tool. Issue CRUD, PR yonetimi, commit/branch listeleme, label yonetimi ve webhook event handling. EKS uzerinde calisir (host agent gerekmez). httpx async client ile GitHub REST API v3 kullanilir.

## Feature Spec

-> `shared/feature-specs/f3-20-f3-01-github-manager-tool.md`

## API Contracts

-> `shared/api-contracts/rest/v1/webhooks.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 9 dosya |
| ios | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- GitHub tool bir "cloud tool"dur - EKS uzerinde calisir, host agent gerekmez. `app/tools/` dizinine yerlestirilir.
- httpx async client kullanilir (PyGithub gibi sync kutuphaneler YASAK). httpx zaten pyproject.toml'da dependency olarak mevcut.
- Rate limit handling kritik: X-RateLimit-Remaining ve X-RateLimit-Reset header'lari izlenmeli, limit yakinsa exponential backoff uygulanmali.
- Onay gerektiren islemler: create_issue, update_issue, close_issue (approval_category: "write_remote").
- Webhook endpoint'i HMAC-SHA256 ile dogrulanmali (X-Hub-Signature-256 header). GITHUB_WEBHOOK_SECRET config'ten alinir.
- Tool schema Claude API formatinda olmali (name, description, input_schema).
- `app/tools/base.py` ile BaseTool abstract class olusturulup, gelecek tool'lar (S3, memory, cost) icin de kullanilabilir temel yapi saglanmali.
- Config'e `github_token` ve `github_webhook_secret` alanlari eklenmeli (Settings class).
- Dependency: F1-03 (Claude AI Orchestrator) - tool_registry zaten mevcut.

## Referans Dokumanlar

| Karar Alani | Referans Dokuman |
|-------------|-----------------|
| Tool tanimlari | `docs/03_AI_Agent_Tool_Layer_Specification.md` (Section 5.2) |
| Webhook endpoint | `docs/02_Backend_API_WebSocket_Specification.md` (Section 5.5) |
| Onay matrisi | `docs/07_Security_Permissions_Cost_Analysis.md` |
| Tool konum matrisi | `docs/03_AI_Agent_Tool_Layer_Specification.md` (Section 5.1) |

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi
