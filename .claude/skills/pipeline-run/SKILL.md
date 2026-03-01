# /pipeline-run

> Feature pipeline'ini uctan uca calistir.

## Kullanim

```
/pipeline-run <PIPELINE_TIPI> <ISSUE_NO>
```

**Parametreler**:
- `PIPELINE_TIPI`: `full` | `standard` | `quick`
- `ISSUE_NO`: GitHub issue numarasi

**Ornekler**:
```
/pipeline-run full 42
/pipeline-run standard 15
/pipeline-run quick 7
```

## Pipeline Tipleri

| Pipeline | Adimlar | Ne Zaman |
|----------|---------|----------|
| `full` | Architect -> Developer -> Tester -> Reviewer | Major feature, yeni ekran, yeni API |
| `standard` | Developer -> Tester | Orta olcekli feature, mevcut API genisletme |
| `quick` | Developer | Infra, config, kucuk bugfix, dokuamntasyon |

## Calisma Adimlari

### Adim 1: Issue Metadata Cek

```bash
gh issue view <ISSUE_NO> --json title,body,labels,assignees,milestone
```

Issue'dan asagidaki bilgileri cikar:
- **Title**: Feature adi
- **Body**: Feature aciklamasi
- **Labels**: `phase:f<N>`, `pipeline:<tip>`, `layer:<katman>`, `status:ready`
- **Milestone**: Faz numarasi (fallback)

Issue `status:ready` label'ina sahip olmali. Degilse hata ver ve cik.

Pipeline tipi belirtilmemisse issue label'indan al (`pipeline:full`, `pipeline:standard`, `pipeline:quick`).

### Adim 2: Slug Olustur

Issue title'dan slug olustur:
- Kucuk harf
- Bosluk -> tire
- Turkce karakter -> ASCII (o -> o, u -> u, s -> s, c -> c, g -> g, i -> i)
- Ozel karakter kaldir
- Max 40 karakter

Ornek: "Chat Ekrani WebSocket Baglantisi" -> `chat-ekrani-websocket-baglantisi`

### Adim 3: Faz Numarasini Belirle

Issue label'larindan `phase:f<N>` label'ini bul.
Label yoksa milestone'dan al.
Ikisi de yoksa `f0` kullan.

### Adim 4: Worktree Olustur

```bash
# develop'u guncelle
git fetch origin develop

# Worktree olustur
BRANCH_NAME="feature/f<FAZ>/<ISSUE_NO>-<slug>"
WORKTREE_DIR=".worktrees/feature-f<FAZ>-<ISSUE_NO>"

git worktree add "$WORKTREE_DIR" -b "$BRANCH_NAME" origin/develop
cd "$WORKTREE_DIR"
```

### Adim 5: Issue Durumunu Guncelle

```bash
gh issue edit <ISSUE_NO> --remove-label "status:ready" --add-label "status:in-progress"
```

### Adim 6: Pipeline Adimlarini Calistir

Pipeline tipine gore agent'lari sirali olarak calistir.

#### 6a. Architect (sadece `full`)

Architect agent'ini calistir. Agent `.claude/agents/architect.md` tanimina gore calisir.

**Girdi**: Issue metadata (title, body, labels)
**Cikti**: Feature spec + API contracts + architect handoff

Dogrulama:
- `shared/feature-specs/f<FAZ>-<ISSUE_NO>-<slug>.md` olusturuldu mu?
- `docs/pipeline/f<FAZ>/<slug>-architect.handoff.md` olusturuldu mu?

Basarisizsa: `status:blocked` label ekle, cik.

#### 6b. Developer (tum pipeline'lar)

Developer agent'ini calistir. Agent `.claude/agents/developer.md` tanimina gore calisir.

**Girdi**:
- full: Architect handoff dosyasi
- standard/quick: Issue body

**Cikti**: Implementasyon kodu + developer handoff

Dogrulama:
- Commit'ler olusturuldu mu?
- `docs/pipeline/f<FAZ>/<slug>-developer.handoff.md` olusturuldu mu?

Basarisizsa (3 retry sonrasi): `status:blocked` label ekle, cik.

#### 6c. Tester (sadece `full` ve `standard`)

Tester agent'ini calistir. Agent `.claude/agents/tester.md` tanimina gore calisir.

**Girdi**: Developer handoff dosyasi
**Cikti**: Test kodu + tester handoff + coverage raporu

Dogrulama:
- Test dosyalari olusturuldu mu?
- Coverage esikleri karsilandi mi? (Backend >=80%, iOS >=70%, Agent >=80%)
- `docs/pipeline/f<FAZ>/<slug>-tester.handoff.md` olusturuldu mu?

Basarisizsa: `status:blocked` label ekle, cik.

#### 6d. Reviewer (sadece `full`)

Reviewer agent'ini calistir. Agent `.claude/agents/reviewer.md` tanimina gore calisir.

**Girdi**: Tum handoff dosyalari (architect + developer + tester)
**Cikti**: Review raporu + reviewer handoff

Dogrulama:
- Review sonucu: ONAYLANDI, DUZELTME GEREKLI, veya REDDEDILDI
- `docs/pipeline/f<FAZ>/<slug>-reviewer.handoff.md` olusturuldu mu?

DUZELTME GEREKLI durumunda:
- Developer agent'i tekrar calistir (review feedback ile)
- Tester agent'i tekrar calistir
- Reviewer agent'i tekrar calistir
- Max 2 tur (toplamda 3 review)

REDDEDILDI durumunda: `status:blocked` label ekle, cik.

### Adim 7: Final Dogrulama

Tum pipeline adimlari tamamlandiktan sonra son dogrulama yap:

```bash
# Backend varsa
cd apps/backend && ruff check app/ && mypy app/ && python -m pytest --cov=app

# iOS varsa
cd apps/ios && xcodebuild build -scheme RafRaf && xcodebuild test -scheme RafRaf

# Agent varsa
cd apps/agent && ruff check agent/ && mypy agent/ && python -m pytest --cov=agent
```

Basarisizsa: Hata logu ile `status:blocked` label ekle.

### Adim 8: PR Olustur

```bash
# Branch'i push et
git push -u origin "$BRANCH_NAME"

# PR olustur
gh pr create \
  --title "feat(<scope>): <Feature Adi> #<ISSUE_NO>" \
  --body "$(cat <<'EOF'
## Ozet
<Feature aciklamasi>

## Pipeline
| Adim | Agent | Durum |
|------|-------|-------|
| Architect | architect | DONE/SKIPPED |
| Developer | developer | DONE |
| Tester | tester | DONE/SKIPPED |
| Reviewer | reviewer | DONE/SKIPPED |

## Coverage
| Platform | Coverage | Esik | Durum |
|----------|----------|------|-------|
| Backend | X% | 80% | PASS |
| iOS | X% | 70% | PASS |
| Agent | X% | 80% | PASS |

## Handoff Dosyalari
- `docs/pipeline/f<FAZ>/<slug>-architect.handoff.md`
- `docs/pipeline/f<FAZ>/<slug>-developer.handoff.md`
- `docs/pipeline/f<FAZ>/<slug>-tester.handoff.md`
- `docs/pipeline/f<FAZ>/<slug>-reviewer.handoff.md`
EOF
)" \
  --base develop \
  --label "agent:pipeline" \
  --label "phase:f<FAZ>" \
  --label "layer:<KATMAN>" \
  --label "pipeline:<TIP>"
```

### Adim 9: Issue Durumunu Guncelle

```bash
gh issue edit <ISSUE_NO> --remove-label "status:in-progress" --add-label "status:review"
```

### Adim 10: Worktree Temizle

Pipeline tamamlaninca worktree'yi kaldirmaya GEREK YOK (PR merge sonrasinda temizlenir).
Ancak basarisizlik durumunda worktree kalabilir:

```bash
# Gerekirse worktree temizleme (manual)
git worktree remove "$WORKTREE_DIR" --force
```

## Hata Yonetimi

| Hata | Aksiyon |
|------|---------|
| Issue bulunamadi | Hata mesaji goster, cik |
| Issue `status:ready` degil | Uyari goster, cik |
| Worktree olusturulamadi | Branch cakismasi kontrol et, cik |
| Agent basarisiz (3 retry sonrasi) | `status:blocked` label, hata comment, cik |
| CI dogrulama basarisiz | `status:blocked` label, hata detayi comment, cik |
| PR olusturulamadi | Manuel PR olusturma talimatlarini goster |

## Cikti

Pipeline tamamlaninca asagidaki bilgileri raporla:

```
Pipeline Tamamlandi!
====================
Issue: #<ISSUE_NO> - <Title>
Pipeline: <TIP>
Branch: feature/f<FAZ>/<ISSUE_NO>-<slug>
PR: #<PR_NO>
Durum: BASARILI / BASARISIZ

Adimlar:
  Architect: DONE / SKIPPED / FAILED
  Developer: DONE / FAILED
  Tester: DONE / SKIPPED / FAILED
  Reviewer: DONE / SKIPPED / FAILED

Coverage:
  Backend: X% (>= 80%)
  iOS: X% (>= 70%)
  Agent: X% (>= 80%)
```
