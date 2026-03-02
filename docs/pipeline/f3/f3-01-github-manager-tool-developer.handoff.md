# Developer Handoff: GitHub Manager Tool

**Issue**: #20
**Branch**: feature/f3/20-f3-01-github-manager-tool
**Tarih**: 2026-03-02
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/tools/__init__.py` | CREATE | Tools package init |
| `app/tools/base.py` | CREATE | BaseTool abstract class - tum cloud tool'lar icin temel yapi |
| `app/tools/github_tool.py` | CREATE | GitHubTool - 12 action destekli Claude tool |
| `app/schemas/github.py` | CREATE | Pydantic frozen modeller (Issue, PR, Commit, Branch, RepoInfo, WebhookResponse) |
| `app/services/github_service.py` | CREATE | Async httpx GitHub API v3 client - rate limit, retry, HMAC dogrulama |
| `app/api/routes/webhooks.py` | CREATE | GitHub webhook receiver endpoint (POST /api/v1/webhooks/github) |
| `app/core/config.py` | MODIFY | github_token, github_webhook_secret alanlari eklendi |
| `app/main.py` | MODIFY | webhooks_router eklendi |

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | Tum dosyalar temiz |
| ruff format | PASS | Tum dosyalar formatli |
| mypy | PASS | Strict mode, 6 dosya kontrol edildi |

## API Kontrat Uyumu

- Webhook endpoint: `shared/api-contracts/rest/v1/webhooks.json` referans alindi
- POST /api/v1/webhooks/github path, method ve response schema uyumlu
- Tool fonksiyonlari Claude API tool schema formatinda (REST endpoint degil)

## Notlar

- `_to_int` ve `_to_str` helper fonksiyonlari: mypy strict mode'da `dict[str, object]` icinden tip-guvenli veri cikarma icin
- httpx zaten pyproject.toml'da mevcut, ek dependency gerekmedi
- Webhook HMAC-SHA256 dogrulama `GitHubService.verify_webhook_signature` static metodu ile
- BaseTool abstract class gelecekteki tool'lar (S3, memory, cost) icin temel olusturur
- Rate limit: X-RateLimit-Remaining < 100 olunca warning log, 403 + X-RateLimit-Reset header ile backoff
- Onay gerektiren action'lar: create_issue, update_issue, close_issue (approval_category: write_remote)
