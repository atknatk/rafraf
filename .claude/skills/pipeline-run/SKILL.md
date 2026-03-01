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
gh issue view <ISSUE_NO> --json title,body,labels,assignees,milestone --repo atknatk/rafraf
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
1. Kucuk harfe cevir
2. Turkce karakterleri ASCII'ye donustur:
   - `ç` -> `c`, `Ç` -> `c`
   - `ğ` -> `g`, `Ğ` -> `g`
   - `ı` -> `i`, `İ` -> `i`
   - `ö` -> `o`, `Ö` -> `o`
   - `ş` -> `s`, `Ş` -> `s`
   - `ü` -> `u`, `Ü` -> `u`
3. Bosluklari tire (`-`) ile degistir
4. Alfanumerik olmayan karakterleri kaldir (tire haric)
5. Ardisik tireleri tek tireye indirge
6. Bas ve sondaki tireleri kaldir
7. Maksimum 40 karakter (son tireden kes)

Ornek: "Chat Ekranı WebSocket Bağlantısı" -> `chat-ekrani-websocket-baglantisi`

### Adim 3: Faz Numarasini Belirle

Issue label'larindan `phase:fX` label'ini bul (ornek: `phase:f1`, `phase:f2`).
Label yoksa milestone'dan al.
Ikisi de yoksa hata ver ve cik: "FAZ numarasi belirlenemedi. Issue'ya `phase:fX` label'i ekleyin."

### Adim 4: Worktree Olustur

```bash
# develop'u guncelle
git fetch origin develop

# Worktree dizinini olustur
mkdir -p .worktrees/

# Worktree olustur
BRANCH_NAME="feature/f<FAZ>/<ISSUE_NO>-<slug>"
WORKTREE_DIR=".worktrees/feature-f<FAZ>-<ISSUE_NO>"

git worktree add "$WORKTREE_DIR" -b "$BRANCH_NAME" origin/develop
cd "$WORKTREE_DIR"
```

### Adim 5: Issue Durumunu Guncelle

```bash
gh issue edit <ISSUE_NO> --remove-label "status:ready" --add-label "status:in-progress" --repo atknatk/rafraf
```

### Adim 6: Pipeline Adimlarini Calistir

Pipeline tipine gore agent'lari sirali olarak calistir.

**Agent calistirma mekanizmasi:**
- Claude Code `Agent` tool'unu kullan
- `subagent_type: "general-purpose"`
- Agent'in `.claude/agents/<name>.md` dosyasini prompt'a dahil et
- Input olarak issue metadata'sini (title, body, labels, issue number) ver
- Agent worktree icerisinde calisir

#### 6a. Architect (sadece `full`)

Architect agent'ini calistir. Agent `.claude/agents/architect.md` tanimina gore calisir.
Claude Code Agent tool ile calistirilir. Pipeline-run skill, Agent tool'u kullanarak `.claude/agents/architect.md` dosyasini okur ve ilgili agent'i baslatir.

**Girdi**: Issue metadata (title, body, labels, issue number)
**Cikti**: Feature spec + API contracts + architect handoff

Dogrulama:
- `shared/feature-specs/f<FAZ>-<ISSUE_NO>-<slug>.md` olusturuldu mu?
- `docs/pipeline/f<FAZ>/<slug>-architect.handoff.md` olusturuldu mu?

Basarisizsa: `status:blocked` label ekle, cik.

#### 6b. Developer (tum pipeline'lar)

Developer agent'ini calistir. Agent `.claude/agents/developer.md` tanimina gore calisir.
Claude Code Agent tool ile calistirilir. Pipeline-run skill, Agent tool'u kullanarak `.claude/agents/developer.md` dosyasini okur ve ilgili agent'i baslatir.

**Girdi**:
- full: Architect handoff dosyasi + issue metadata (title, body, labels, issue number)
- standard/quick: Issue body + issue metadata (title, body, labels, issue number)

**Cikti**: Implementasyon kodu + developer handoff

Dogrulama:
- Commit'ler olusturuldu mu?
- `docs/pipeline/f<FAZ>/<slug>-developer.handoff.md` olusturuldu mu?

Basarisizsa (3 retry sonrasi): `status:blocked` label ekle, cik.

#### 6c. Tester (sadece `full` ve `standard`)

Tester agent'ini calistir. Agent `.claude/agents/tester.md` tanimina gore calisir.
Claude Code Agent tool ile calistirilir. Pipeline-run skill, Agent tool'u kullanarak `.claude/agents/tester.md` dosyasini okur ve ilgili agent'i baslatir.

**Girdi**: Developer handoff dosyasi + issue metadata (title, body, labels, issue number)
**Cikti**: Test kodu + tester handoff + coverage raporu

Dogrulama:
- Test dosyalari olusturuldu mu?
- Coverage esikleri karsilandi mi? (Backend >=80%, iOS >=70%, Agent >=80%)
- `docs/pipeline/f<FAZ>/<slug>-tester.handoff.md` olusturuldu mu?

Basarisizsa: `status:blocked` label ekle, cik.

#### 6d. Reviewer (sadece `full`)

Reviewer agent'ini calistir. Agent `.claude/agents/reviewer.md` tanimina gore calisir.
Claude Code Agent tool ile calistirilir. Pipeline-run skill, Agent tool'u kullanarak `.claude/agents/reviewer.md` dosyasini okur ve ilgili agent'i baslatir.

**Girdi**: Tum handoff dosyalari (architect + developer + tester) + issue metadata (title, body, labels, issue number)
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

Tum pipeline adimlari tamamlandiktan sonra son dogrulama yap.

**Katman tespiti**: Hangi katmanlarin dogrulanacagini belirle:
```bash
git diff --name-only develop...HEAD
```
- `apps/backend/` varsa backend dogrula
- `apps/ios/` varsa ios dogrula
- `apps/agent/` varsa agent dogrula

```bash
# Backend varsa
cd apps/backend && ruff check app/ && mypy app/ && python -m pytest --cov=app

# iOS varsa
cd apps/ios && xcodebuild build -project apps/ios/RafRaf.xcodeproj -scheme RafRaf && xcodebuild test -project apps/ios/RafRaf.xcodeproj -scheme RafRaf

# Agent varsa
cd apps/agent && ruff check agent/ && mypy agent/ && python -m pytest --cov=agent
```

Basarisizsa: Hata logu ile `status:blocked` label ekle (`--repo atknatk/rafraf`).

### Adim 8: PR Olustur

**Scope belirleme**: Issue label'larindan `layer:*` label'ini oku. Birden fazla layer varsa en kritik olani kullan (oncelik sirasi: backend > ios > agent > infra > docs > shared).

```bash
# Branch'i push et
git push -u origin "$BRANCH_NAME"

# PR olustur
gh pr create \
  --title "<type>(<scope>): <Feature Adi> #<ISSUE_NO>" \
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

---
Generated by RafRaf AI Pipeline
EOF
)" \
  --base develop \
  --label "agent:pipeline" \
  --label "phase:f<FAZ>" \
  --label "layer:<KATMAN>" \
  --label "pipeline:<TIP>" \
  --repo atknatk/rafraf
```

**Not**: Pipeline-run kendi PR template'ini kullanir. Pipeline disinda PR olusturmak icin `/create-pr` skill'ini kullanin.

### Adim 9: Issue Durumunu Guncelle

Status degistirirken once eski status label'ini kaldir:

```bash
gh issue edit <ISSUE_NO> --remove-label "status:in-progress" --add-label "status:review" --repo atknatk/rafraf
```

### Adim 10: Worktree Temizle

- **Pipeline basarili**: Worktree, PR merge sonrasi silinir. `git worktree remove "$WORKTREE_DIR"`
- **Pipeline basarisiz**: Worktree muhafaza edilir. Issue'ya `status:blocked` eklenir. Debug icin worktree korunur.

```bash
# Basarili pipeline sonrasi (merge sonrasi)
git worktree remove "$WORKTREE_DIR"

# Basarisiz pipeline -> worktree muhafaza et, status:blocked ekle
gh issue edit <ISSUE_NO> --remove-label "status:in-progress" --add-label "status:blocked" --repo atknatk/rafraf
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
