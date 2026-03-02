# Developer Handoff: CI/CD GitHub Actions (backend + iOS + agent)

**Issue**: #2
**Branch**: feature/f0/2-cicd-github-actions
**Tarih**: 2026-03-02
**Sonraki Agent**: NONE (quick pipeline)

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `.github/workflows/backend-ci.yml` | CREATE | Backend CI workflow: ruff check, ruff format, mypy, pytest with coverage |
| `.github/workflows/agent-ci.yml` | CREATE | Agent CI workflow: ruff check, ruff format, mypy, pytest with coverage |
| `.github/workflows/ios-ci.yml` | CREATE | iOS CI workflow: xcodebuild build + test (macos-latest, Xcode 16, iPhone 16 sim) |
| `.github/workflows/pr-gate.yml` | CREATE | PR Gate: path-filtered combined gate for all platforms |
| `.github/workflows/auto-merge.yml` | CREATE | Auto-merge: agent:pipeline label ile squash merge after CI passes |

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| YAML syntax | PASS | Tum workflow dosyalari gecerli YAML |

## Notlar

- Backend ve Agent CI: ubuntu-latest, Python 3.12, pip install -e ".[dev]"
- iOS CI: macos-latest, Xcode 16.2, iPhone 16 simulator, code signing disabled
- PR Gate: dorny/paths-filter ile path-based change detection, sadece ilgili platform gate'leri calisir
- Auto-merge: workflow_run event ile trigger, actions/github-script ile squash merge
- Tum workflow'lar push (develop, main) ve PR (develop, main) event'lerinde tetiklenir
- iOS build ve test ayrı job'lar olarak needs dependency ile siralanir
