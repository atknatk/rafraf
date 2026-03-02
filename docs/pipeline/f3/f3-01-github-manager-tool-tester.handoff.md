# Tester Handoff: GitHub Manager Tool

**Issue**: #20
**Branch**: feature/f3/20-f3-01-github-manager-tool
**Tarih**: 2026-03-02
**Sonraki Agent**: reviewer

## Test Ozeti

| Kategori | Dosya | Test Sayisi | Durum |
|----------|-------|-------------|-------|
| Unit - Service | `tests/unit/test_services/test_github_service.py` | 24 | PASS |
| Unit - Tool | `tests/unit/test_tools/test_github_tool.py` | 20 | PASS |
| Integration - API | `tests/integration/test_api/test_webhook_endpoints.py` | 8 | PASS |
| Contract | `tests/contract/test_webhook_contracts.py` | 5 | PASS |
| **Toplam** | | **56** | **ALL PASS** |

## Test Kapsami

### Unit Tests - GitHubService (24 test)
- `_to_int` helper: int, str, float, None, invalid, custom default (6)
- `_to_str` helper: str, int, None, custom default (4)
- `verify_webhook_signature`: valid, invalid, missing prefix (3)
- `format_result`: dict, list, pydantic model (3)
- `list_issues`: parse response, skip PRs (2)
- `get_issue`: parse response (1)
- Rate limit: server error retry, client error no retry (2)
- `list_prs`: parse response (1)
- `list_commits`: parse response (1)
- `get_repo_info`: parse response (1)

### Unit Tests - GitHubTool (20 test)
- `get_definition`: name, schema, required fields (3)
- `requires_action_approval`: create/update/close_issue (True), list_issues/get_pr/add_labels (False) (6)
- `execute`: missing action, missing repo, unknown action (3)
- `execute` dispatch: list_issues, get_issue (requires number), list_commits, get_repo_info (4)
- Error handling: service error returns JSON (1)
- Registration: adds to registry, handler callable (2)
- Missing: get_issue_requires_issue_number (1)

### Integration Tests - Webhook Endpoint (8 test)
- Event handling: ping, issues, pull_request, push (4)
- Unsupported event: star -> ignored (1)
- Signature: valid accepted, invalid rejected (401), missing rejected (401) (3)

### Contract Tests (5 test)
- Contract file exists
- Endpoint path matches `/api/v1/webhooks/github`
- Endpoint method matches `POST`
- Response body has required fields (status, message)
- Response status values match enum

## Dogrulama

```
$ cd apps/backend && python -m pytest tests/ -v
======================== 56 passed, 1 warning in 1.75s =========================
```

## Notlar

- Tum testler `unittest.mock.patch` ile izole edilmis, dis servis bagimliligi yok
- httpx.Response mock'lari gercek GitHub API yanitlarina yakin
- Contract testleri `shared/api-contracts/rest/v1/webhooks.json` dosyasini runtime'da okur
- FastAPI TestClient ile webhook endpoint'leri gercek HTTP katmanindan test edilir
