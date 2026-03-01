# RafRaf -- Pipeline Komut Referansi

Bu dokuman AI pipeline'inda kullanilan slash komutlarini (skill'leri) aciklar.

---

## Pipeline Mimarisi

### Agent Rolleri (4 rol)

Her agent, Claude Code Agent tool ile `.claude/agents/<name>.md` tanimini kullanarak calistirilir.

| Agent         | Model  | Gorev                                        |
|---------------|--------|----------------------------------------------|
| **architect** | Opus   | Feature spec + API kontrat + dosya sahipligi |
| **developer** | Opus   | Kod implementasyonu (backend/ios/agent)      |
| **tester**    | Sonnet | Test yazma + CI dogrulama                    |
| **reviewer**  | Opus   | Kod review + kalite gate                     |

### Pipeline Tipleri

| Pipeline   | Adimlar                                      | Ne Zaman                                    |
|------------|----------------------------------------------|---------------------------------------------|
| `full`     | Architect -> Developer -> Tester -> Reviewer | Major feature, yeni ekran, yeni API         |
| `standard` | Developer -> Tester                          | Orta olcekli feature, mevcut API genisletme |
| `quick`    | Developer                                    | Infra, config, kucuk bugfix, dokumantasyon  |

### Slug Olusturma Kurallari

Issue title'dan slug olusturulur:

1. Kucuk harfe cevir
2. Turkce karakterleri ASCII'ye donustur: c->c, g->g, i->i, o->o, s->s, u->u, C->c, G->g, I->i, O->o, S->s, U->u
3. Bosluklari tire (`-`) ile degistir
4. Ozel karakterleri kaldir (tire haric)
5. Ardisik tireleri tek tireye indirge
6. Bas ve sondaki tireleri kaldir
7. Maksimum 40 karakter (son tireden kes)

Ornek: "Chat Ekrani WebSocket Baglantisi" -> `chat-ekrani-websocket-baglantisi`

---

## /pipeline-run

> Feature pipeline'ini uctan uca calistir.

### pipeline-run Kullanim

```bash
/pipeline-run <PIPELINE_TIPI> <ISSUE_NO>
```

**Parametreler**:

- `PIPELINE_TIPI`: `full` | `standard` | `quick`
- `ISSUE_NO`: GitHub issue numarasi (bare numara, ornek: `42`)

**Ornekler**:

```bash
/pipeline-run full 42
/pipeline-run standard 15
/pipeline-run quick 7
```

### pipeline-run Calisma Akisi

1. Issue metadata'sini cek (`gh issue view <ISSUE_NO>`)
2. Issue title'dan slug olustur
3. Faz numarasini belirle (`phase:f<N>` label'indan)
4. Worktree olustur: `feature/f<FAZ>/<ISSUE_NO>-<slug>` (base: `develop`)
5. Issue durumunu `status:in-progress` yap
6. Pipeline tipine gore agent'lari sirali calistir (Architect -> Developer -> Tester -> Reviewer)
7. Final dogrulama (lint + test + coverage)
8. PR olustur (`--base develop`, `agent:pipeline` label ile)
9. Issue durumunu `status:review` yap

---

## /queue-run

> Feature kuyrugundan sirali olarak issue'lari isle.

### queue-run Kullanim

```bash
/queue-run
/queue-run --source issues
/queue-run --source file
/queue-run --limit 3
/queue-run --dry-run
```

**Parametreler**:

- `--source`: `issues` (GitHub Issues, varsayilan) veya `file` (`scripts/feature-queue.jsonl`)
- `--limit`: Maksimum islenecek issue sayisi (varsayilan: sinirsiz)
- `--dry-run`: Isleme yapmadan siralamayi goster

### queue-run Calisma Akisi

1. `status:ready` label'li issue'lari al ve sirala (faz -> oncelik -> issue no)
2. Bagimlilik kontrolu yap (`depends-on: #X` kontrol)
3. Her issue icin pipeline tipini belirle (label'dan veya varsayilan `standard`)
4. `/pipeline-run` ile pipeline calistir
5. Basarili: `status:review` label ekle. Basarisiz: kuyruqu durdur, `status:blocked` label ekle
6. Engelleri kalkan bagimli issue'lara `status:ready` ekle
7. Sonraki issue'ya gec veya kuyruk raporunu goster

---

## /verify

> Kod kalitesi ve test dogrulama komutu.

### verify Kullanim

```bash
/verify all
/verify backend
/verify ios
/verify agent
/verify test
```

**Parametreler**:

- `all`: Tum katmanlari dogrula (backend + ios + agent)
- `backend`: Sadece backend dogrulama
- `ios`: Sadece iOS dogrulama
- `agent`: Sadece agent dogrulama
- `test`: Sadece test calistir (tum katmanlar)

### Dogrulama Adimlari

**Backend**: ruff check -> ruff format -> mypy strict -> pytest + coverage (>= 80%)

**iOS**: swiftlint -> xcodebuild build (`-scheme RafRaf`) -> xcodebuild test (`-scheme RafRaf`, `-enableCodeCoverage YES`) -> coverage (>= 70%)

**Agent**: ruff check -> ruff format -> mypy strict -> pytest + coverage (>= 80%)

---

## /feature-branch

> Feature branch olusturma komutu.

### feature-branch Kullanim

```bash
/feature-branch <FAZ> <ISSUE_NO> <ACIKLAMA>
```

**Parametreler**:

- `FAZ`: Faz numarasi (1, 2, 3, ...)
- `ISSUE_NO`: GitHub issue numarasi (bare numara)
- `ACIKLAMA`: Branch aciklamasi (bosluklu, slug'a cevirilecek)

**Ornekler**:

```bash
/feature-branch 1 42 Chat ekrani websocket baglantisi
/feature-branch 2 15 Sesli komut entegrasyonu
/feature-branch 1 7 Auth JWT token
```

### Branch Format

```text
feature/f<FAZ>/<ISSUE_NO>-<slug>
```

Ornekler:

```text
feature/f1/42-chat-ekrani-websocket-baglantisi
feature/f2/15-sesli-komut-entegrasyonu
feature/f1/7-auth-jwt-token
```

### feature-branch Calisma Akisi

1. Aciklama metninden slug olustur (slug kurallarina gore)
2. `develop` branch'ini guncelle (`git fetch origin develop`)
3. Ayni issue icin mevcut branch var mi kontrol et
4. Branch olustur: `git checkout -b feature/f<FAZ>/<ISSUE_NO>-<slug>`
5. Dogrula ve raporla

---

## /create-pr

> Feature branch'ini push et ve Pull Request olustur.

### create-pr Kullanim

```bash
/create-pr
/create-pr --pipeline full
/create-pr --base develop
/create-pr --draft
```

**Parametreler**:

- `--pipeline`: Pipeline tipi (`full`, `standard`, `quick`). Otomatik algilanir.
- `--base`: Hedef branch (varsayilan: `develop`)
- `--draft`: Draft PR olustur

### create-pr Calisma Akisi

1. Mevcut branch'i analiz et (`feature/f<FAZ>/<ISSUE_NO>-<slug>` formatinda mi?)
2. Commit kontrolu yap (en az 1 commit gerekli)
3. Branch'i push et (`git push -u origin`)
4. Issue bilgilerini cek (`gh issue view`)
5. Etkilenen katmanlari belirle (degisen dosyalardan)
6. Handoff dosyalarini oku (varsa)
7. PR olustur (`gh pr create --base develop --label "agent:pipeline"`)
8. Issue durumunu `status:review` yap

### PR Formati

```text
Title: <type>(<scope>): <Feature Adi> #<ISSUE_NO>
Base: develop
Labels: agent:pipeline, phase:f<FAZ>, layer:<KATMAN>, pipeline:<TIP>
```

---

## Tipik Is Akisi

```bash
# 1. Feature branch olustur
/feature-branch 1 15 health endpoint

# 2. Feature'i implement et
# ... kod degisiklikleri ...

# 3. Dogrulama yap
/verify backend

# 4. PR olustur
/create-pr

# Veya tek komutla pipeline calistir:
/pipeline-run standard 15

# Veya kuyruktan sirali isle:
/queue-run --source issues --limit 3
```

---

## Agent Calistirma

Agent'lar Claude Code Agent tool ile calistirilir. Her agent `.claude/agents/<name>.md` dosyasindaki tanimi kullanir.

```text
Agent tanimlari:
  .claude/agents/architect.md
  .claude/agents/developer.md
  .claude/agents/tester.md
  .claude/agents/reviewer.md
```

Agent calistirma mekanizmasi: Claude Code Agent tool ile `subagent_type` parametresi ve ilgili agent tanim dosyasi kullanilarak calistirilir.
