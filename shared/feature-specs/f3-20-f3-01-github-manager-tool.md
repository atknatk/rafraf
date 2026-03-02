# Feature: GitHub Manager Tool

**Issue**: #20
**Faz**: F3
**Katmanlar**: backend
**Pipeline**: full
**Tarih**: 2026-03-02

## Ozet

Claude AI Orchestrator icin GitHub islemlerini gerceklestiren tool. Issue CRUD (olusturma, okuma, guncelleme, kapatma), PR yonetimi (listeleme, detay, review), commit/branch listeleme, label yonetimi ve webhook event handling islemlerini saglayan bir cloud tool'dur. EKS uzerinde calisir (host agent gerekmez). GitHub API v3 (REST) httpx async client ile kullanilir. Rate limit handling (5000 req/saat) dahildir.

## Degisecek Dosyalar

### Backend (`apps/backend/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/tools/__init__.py` | CREATE | Tools package init |
| `app/tools/github_tool.py` | CREATE | GitHub Manager tool - tum GitHub islemleri |
| `app/tools/base.py` | CREATE | BaseTool abstract sinifi |
| `app/schemas/github.py` | CREATE | GitHub tool Pydantic request/response modelleri |
| `app/api/routes/webhooks.py` | CREATE | GitHub webhook receiver endpoint |
| `app/services/github_service.py` | CREATE | GitHub API erisim katmani (httpx async) |
| `app/core/config.py` | MODIFY | GitHub-specific config alanlari (token, webhook secret) |
| `app/main.py` | MODIFY | Webhook router ve tool registration ekleme |
| `app/orchestrator/tool_registry.py` | MODIFY | github_manager tool kaydini destekleme |

## API Endpoints

### REST
| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| POST | `/api/v1/webhooks/github` | GitHub webhook payload | `WebhookResponse` | GitHub event receiver (PR merge, issue update, push) |

### Tool Fonksiyonlari (Claude Tool Calling)

Bu fonksiyonlar REST endpoint degil, Claude tool schema olarak tanimlanir. Claude API tool_call ile cagirilir, backend icinde execute edilir.

| Fonksiyon | Parametreler | Aciklama | Onay |
|-----------|-------------|----------|------|
| `list_issues` | `repo`, `state?`, `labels?`, `page?`, `per_page?` | Issue listele | Hayir |
| `get_issue` | `repo`, `issue_number` | Issue detayi | Hayir |
| `create_issue` | `repo`, `title`, `body?`, `labels?`, `assignees?` | Yeni issue olustur | EVET |
| `update_issue` | `repo`, `issue_number`, `title?`, `body?`, `state?`, `labels?` | Issue guncelle | EVET |
| `close_issue` | `repo`, `issue_number`, `comment?` | Issue kapat | EVET |
| `list_prs` | `repo`, `state?`, `page?`, `per_page?` | PR listele | Hayir |
| `get_pr` | `repo`, `pr_number` | PR detayi + diff ozeti | Hayir |
| `list_commits` | `repo`, `branch?`, `limit?` | Commit gecmisi | Hayir |
| `list_branches` | `repo` | Branch listesi | Hayir |
| `get_repo_info` | `repo` | Repo istatistikleri | Hayir |
| `add_labels` | `repo`, `issue_number`, `labels` | Label ekle | Hayir |
| `remove_labels` | `repo`, `issue_number`, `labels` | Label cikar | Hayir |

## Data Model

### Pydantic Models

```python
class GitHubToolInput(BaseModel):
    """GitHub tool icin Claude API input schema."""
    model_config = ConfigDict(frozen=True)

    action: str  # list_issues, get_issue, create_issue, vb.
    repo: str  # owner/repo formatinda
    issue_number: int | None = None
    pr_number: int | None = None
    title: str | None = None
    body: str | None = None
    comment: str | None = None
    state: str | None = None  # open, closed, all
    labels: list[str] | None = None
    assignees: list[str] | None = None
    branch: str | None = None
    limit: int = 10
    page: int = 1
    per_page: int = 30


class GitHubIssue(BaseModel):
    """GitHub issue modeli."""
    model_config = ConfigDict(frozen=True)

    number: int
    title: str
    state: str
    body: str | None = None
    labels: list[str]
    assignees: list[str]
    created_at: str
    updated_at: str
    html_url: str


class GitHubPullRequest(BaseModel):
    """GitHub pull request modeli."""
    model_config = ConfigDict(frozen=True)

    number: int
    title: str
    state: str
    body: str | None = None
    head_branch: str
    base_branch: str
    mergeable: bool | None = None
    additions: int
    deletions: int
    changed_files: int
    html_url: str
    created_at: str
    updated_at: str


class GitHubCommit(BaseModel):
    """GitHub commit modeli."""
    model_config = ConfigDict(frozen=True)

    sha: str
    message: str
    author: str
    date: str


class GitHubBranch(BaseModel):
    """GitHub branch modeli."""
    model_config = ConfigDict(frozen=True)

    name: str
    sha: str
    protected: bool


class GitHubRepoInfo(BaseModel):
    """GitHub repo istatistikleri."""
    model_config = ConfigDict(frozen=True)

    full_name: str
    description: str | None = None
    default_branch: str
    open_issues_count: int
    forks_count: int
    stargazers_count: int
    language: str | None = None
    html_url: str


class WebhookEvent(BaseModel):
    """GitHub webhook event modeli."""
    action: str
    event_type: str
    repository: str
    sender: str
    payload: dict[str, object]


class WebhookResponse(BaseModel):
    """Webhook response modeli."""
    status: str
    message: str
```

## Business Rules

1. GitHub API erisimi GITHUB_TOKEN environment variable ile saglanir
2. Rate limit: 5000 istek/saat (authenticated). Rate limit header'lari (X-RateLimit-Remaining, X-RateLimit-Reset) izlenir, limit yaklasinca retry with backoff uygulanir
3. Issue/PR olusturma ve kapatma islemleri ONAY GEREKTIRIR (approval_category: "write_remote")
4. Okuma islemleri (list, get) onay gerektirmez
5. Label ekleme/cikarma onay gerektirmez (dusuk riskli islem)
6. Webhook endpoint'i GITHUB_WEBHOOK_SECRET ile HMAC-SHA256 dogrulamasi yapar
7. Tool EKS uzerinde calisir, host agent gerekmez (cloud tool)
8. httpx async client kullanilir (PyGithub yerine lightweight cozum)
9. Tum API cagrilari structured logging ile kayit altina alinir

## Test Requirements

### Backend
- [ ] Unit test: GitHubService her action icin (mock httpx)
- [ ] Unit test: Webhook HMAC signature dogrulama
- [ ] Unit test: Rate limit handling
- [ ] Unit test: Pydantic schema validation (input/output)
- [ ] Unit test: Tool registration ve handler
- [ ] Integration test: Webhook endpoint (test client)
- [ ] Contract test: API kontrat uyumu

## Acceptance Criteria

- [ ] Issue CRUD (olustur, oku, guncelle, kapat) calisiyor
- [ ] PR listeleme ve detay getirme calisiyor
- [ ] Commit/branch listeleme calisiyor
- [ ] Label yonetimi (ekle/cikar) calisiyor
- [ ] Webhook event handling calisiyor (PR merge, issue update)
- [ ] Rate limit handling (backoff + retry) calisiyor
- [ ] Tool tanimlari Claude tool schema formatinda
- [ ] Onay gerektiren islemler dogru isaretlenmis
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
