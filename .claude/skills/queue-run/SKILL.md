# /queue-run

> Feature kuyrugundan sirali olarak issue'lari isle.

## Kullanim

```
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

## Kaynak Formatlari

### GitHub Issues (varsayilan)

`status:ready` label'ina sahip issue'lari sirala:

```bash
gh issue list --label "status:ready" --json number,title,labels,milestone --limit 100 --repo atknatk/rafraf
```

**Siralama onceligi**:
1. Faz numarasi (kucukten buyuge): `phase:f1` < `phase:f2` < `phase:f3`
2. Oncelik label'i: `priority:critical` > `priority:high` > `priority:medium` > `priority:low`
3. Issue numarasi (kucukten buyuge): #1 < #2 < #3

### Feature Queue Dosyasi

`scripts/feature-queue.jsonl` dosyasindan oku:

```jsonl
{"id": "F0-01", "issue": 1, "title": "Repo scaffold + monorepo setup", "phase": "f0", "layer": "infra", "pipeline": "quick", "depends_on": [], "status": "ready"}
{"id": "F1-01", "issue": 7, "title": "FastAPI WebSocket server", "phase": "f1", "layer": "backend", "pipeline": "full", "depends_on": [6], "status": "ready"}
{"id": "F1-02", "issue": 8, "title": "JWT authentication system", "phase": "f1", "layer": "backend", "pipeline": "full", "depends_on": [6], "status": "ready"}
```

**JSONL alan aciklamalari**:
- `id`: Faz-sira formati (F0-01, F1-02, vb.)
- `issue`: GitHub issue numarasi (bare number, `#` veya prefix yok)
- `title`: Feature adi
- `phase`: Faz kodu (f0, f1, f2, ...)
- `layer`: Katman (backend, ios, agent, infra, fullstack)
- `pipeline`: Pipeline tipi (full, standard, quick)
- `depends_on`: Bagimli issue numaralari dizisi (bos dizi = bagimlilik yok)
- `status`: Durum (ready, blocked, in-progress, review, merged)

## Calisma Adimlari

### Adim 1: Issue Listesini Al

Kaynaga gore issue listesini al ve sirala.

```bash
# GitHub Issues
gh issue list --label "status:ready" --json number,title,labels,milestone --limit 100 --repo atknatk/rafraf

# Veya dosyadan
cat scripts/feature-queue.jsonl
```

### Adim 2: Bagimlilik Kontrolu

Her issue icin bagimliliklarin cozulup cozulmedigini kontrol et.

**GitHub Issues icin**:
- Issue body'sinde `depends-on: #X, #Y` satirini ara
- Bagimliliklarin `status:merged` label'ina sahip olup olmadigini kontrol et

**Queue dosyasi icin**:
- `depends_on` dizisindeki issue numaralarini kontrol et
- Her bagimli issue'nun `status:merged` label'ina sahip olup olmadigini kontrol et

```bash
# Bagimlilik kontrol
for DEP in <depends_on>; do
  gh issue view $DEP --json labels --repo atknatk/rafraf | grep "status:merged"
done
```

Bagimliliklari cozulmemis issue'lari atla, sonraki issue'ya gec.

### Adim 3: Pipeline Tipini Belirle

Issue label'larindan pipeline tipini al:
- `pipeline:full` -> full
- `pipeline:standard` -> standard
- `pipeline:quick` -> quick
- Label yoksa -> `standard` (varsayilan)

### Adim 4: Pipeline Calistir (Context-Isolated)

**CRITICAL — Memory izolasyonu:** `/pipeline-run`'i skill olarak cagirMA. Bunun yerine
**Agent subagent** olarak calistir. Boylece tum context (dosya okumalari, build ciktilari,
git islemleri, subagent orchestration) izole kalir ve bittiginde garbage-collected olur.
Ana conversation'a sadece kisa ozet doner.

```
Agent(subagent_type="general-purpose", model="opus", mode="bypassPermissions")

Prompt:
"Load and follow the /pipeline-run skill instructions by reading .claude/skills/pipeline-run/SKILL.md

Run pipeline: /pipeline-run <pipeline_tipi> <issue_no>

Execute ALL steps from the skill file including worktree setup, agent coordination, PR creation, CI wait, and merge.
At the end, respond with ONLY this summary:

RESULT: SUCCESS or FAILED
PR: <url or none>
ISSUE: <issue_no>
ERROR: <short error description if failed, or none>"
```

Parse the subagent's RESULT line to determine success/failure.
If FAILED, extract ERROR for the issue comment.

Pipeline tipi JSONL dosyasindaki `pipeline` alanindan veya issue label'indan alinir.

### Adim 5: Sonuc Degerlendirme

Pipeline-run artik merge'u dahil ediyor (PR olustur -> CI bekle -> merge bekle).

**Basarili** (merge tamamlandi):
- Pipeline-run PR'i olusturdu, CI'i bekledi, merge'u onayladi
- Issue `status:merged` label'i ile kapandi
- develop branch'i guncellendi (`git fetch origin develop`)
- Sonraki adima (Adim 6 — bagimlilik cozme) gec

**Basarisiz**:
- Pipeline-run `status:blocked` label ekledi
- Kuyrugu **DURDUR** — basarisizlik durumunda sonraki issue'lara gecme (bagimliliklari etkileyebilir)

### Adim 6: Engelleri Kaldirma (Merge Sonrasi)

Merge tamamlandiktan sonra, bu issue'ya bagimli olan diger issue'larin
engellerinin kalkip kalkmedigini kontrol et.

**Bagimli issue'lari bul**: JSONL dosyasindan `depends_on` dizisinde `<ISSUE_NO>` iceren satirlari ara.

```bash
# Tum bagimliliklari cozulmus issue'lara status:ready ekle, status:blocked kaldir
for ISSUE in <dependent_issues>; do
  ALL_DEPS_RESOLVED=true
  for DEP in <issue_dependencies>; do
    if ! gh issue view $DEP --json labels --repo atknatk/rafraf | grep -q "status:merged"; then
      ALL_DEPS_RESOLVED=false
      break
    fi
  done
  if [ "$ALL_DEPS_RESOLVED" = true ]; then
    gh issue edit $ISSUE --remove-label "status:blocked" --add-label "status:ready" --repo atknatk/rafraf
    echo "Issue #$ISSUE engeli kaldirildi -> status:ready"
  fi
done
```

**Ornek**: F0 issue #6 (Backend scaffold) merge oldu.
- #7 (FastAPI WS) `depends_on: [6]` → #6 merged ✓ → `status:blocked` -> `status:ready`
- #8 (JWT auth) `depends_on: [6]` → #6 merged ✓ → `status:blocked` -> `status:ready`
- #9 (AI Orchestrator) `depends_on: [7]` → #7 henuz merged degil → `status:blocked` kalir

Bu sayede faz gecisleri otomatik olur: F0 task'lari merge oldukca F1 task'lari `status:ready` olur ve kuyruga girer.

### Adim 7: Sonraki Issue

Kuyrukta daha fazla `status:ready` issue varsa Adim 2'ye don.
Yoksa veya `--limit`'e ulasilmissa kuyrugun sonucu raporla.

## Dry Run Modu

`--dry-run` ile sadece siralamayi goster, islem yapma:

```
Queue Siralama (Dry Run)
========================
1. #1  [full]     Auth sistemi              (bagimlilik: yok)          READY
2. #3  [standard] Profil sayfasi            (bagimlilik: #1)           READY (#1 merged)
3. #2  [full]     Chat ekrani               (bagimlilik: #1)           READY (#1 merged)
4. #4  [full]     Sesli komut               (bagimlilik: #2, #3)      BLOCKED (#2 not merged)

Islenecek: 3 issue
Engelli: 1 issue
```

## Hata Yonetimi

| Hata | Aksiyon |
|------|---------|
| `status:ready` issue yok | "Kuyruk bos" mesaji, cik |
| Bagimlilik cozulmemis | Issue'yu atla, sonrakine gec |
| Pipeline basarisiz | Kuyruqu durdur, rapor goster |
| Queue dosyasi bulunamadi | Hata mesaji, `--source issues` oner |
| Rate limit (GitHub API) | 60 saniye bekle, tekrar dene |

## Cikti

Kuyruk tamamlaninca asagidaki raporu goster:

```
Queue Sonucu
============
Kaynak: GitHub Issues / feature-queue.jsonl
Islenen: X issue
Basarili: Y issue
Basarisiz: Z issue
Atlanan (bagimlilik): W issue

Detay:
  #1  Auth sistemi        -> BASARILI  (PR #10)
  #3  Profil sayfasi      -> BASARILI  (PR #11)
  #2  Chat ekrani         -> BASARISIZ (status:blocked)
  #4  Sesli komut         -> ATLANDI   (bagimlilik: #2)

Engeli Kalkan Issue'lar:
  #3  (bagimlilik #1 cozuldu -> status:ready eklendi)
```

## Guvenlik

- Ayni anda sadece 1 issue islenir (paralel pipeline YOK)
- Her pipeline kendi worktree'sinde calisir (izolasyon)
- Basarisiz pipeline sonrasi kuyruk durur (cascade failure onlemi)
- `--limit` ile kontrol saglanir (malzeme testi icin limit:1 kullan)
