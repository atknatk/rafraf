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
gh issue list --label "status:ready" --json number,title,labels,milestone --limit 100
```

**Siralama onceligi**:
1. Faz numarasi (kucukten buyuge): `phase:f1` < `phase:f2` < `phase:f3`
2. Oncelik label'i: `priority:critical` > `priority:high` > `priority:medium` > `priority:low`
3. Issue numarasi (kucukten buyuge): #1 < #2 < #3

### Feature Queue Dosyasi

`scripts/feature-queue.jsonl` dosyasindan oku:

```jsonl
{"issue": 1, "phase": "f1", "pipeline": "full", "depends_on": [], "title": "Auth sistemi"}
{"issue": 2, "phase": "f1", "pipeline": "full", "depends_on": [1], "title": "Chat ekrani"}
{"issue": 3, "phase": "f1", "pipeline": "standard", "depends_on": [1], "title": "Profil sayfasi"}
{"issue": 4, "phase": "f2", "pipeline": "full", "depends_on": [2, 3], "title": "Sesli komut"}
```

## Calisma Adimlari

### Adim 1: Issue Listesini Al

Kaynaga gore issue listesini al ve sirala.

```bash
# GitHub Issues
gh issue list --label "status:ready" --json number,title,labels,milestone --limit 100

# Veya dosyadan
cat scripts/feature-queue.jsonl
```

### Adim 2: Bagimlilik Kontrolu

Her issue icin bagimliliklarin cozulup cozulmedigini kontrol et.

**GitHub Issues icin**:
- Issue body'sinde `depends-on: #X, #Y` satirini ara
- Veya `depends-on:X` label'ini kontrol et
- Bagimliliklarin `status:merged` label'ina sahip olup olmadigini kontrol et

**Queue dosyasi icin**:
- `depends_on` dizisindeki issue'larin `status:merged` olup olmadigini kontrol et

```bash
# Bagimlilik kontrol
for DEP in <depends_on>; do
  gh issue view $DEP --json labels | grep "status:merged"
done
```

Bagimliliklari cozulmemis issue'lari atla, sonraki issue'ya gec.

### Adim 3: Pipeline Tipini Belirle

Issue label'larindan pipeline tipini al:
- `pipeline:full` -> full
- `pipeline:standard` -> standard
- `pipeline:quick` -> quick
- Label yoksa -> `standard` (varsayilan)

### Adim 4: Pipeline Calistir

`/pipeline-run` skill'ini calistir:

```
/pipeline-run <pipeline_tipi> <issue_no>
```

### Adim 5: Sonuc Degerlendirme

Pipeline sonucuna gore:

**Basarili**:
```bash
# Issue durumunu guncelle
gh issue edit <ISSUE_NO> --remove-label "status:in-progress" --add-label "status:review"
```

**Basarisiz**:
```bash
# Issue'yu blocked olarak isaretle
gh issue edit <ISSUE_NO> --remove-label "status:in-progress" --add-label "status:blocked"

# Kuyrugu DURDUR — basarisizlik durumunda sonraki issue'lara gecme
# (bagimliliklari etkileyebilir)
```

### Adim 6: Engelleri Kaldirma (Basarili Pipeline Sonrasi)

Pipeline basarili olduktan sonra, bu issue'ya bagimli olan diger issue'larin
engellerinin kalkip kalkmdigini kontrol et:

```bash
# Bu issue'ya bagimli issue'lari bul
gh issue list --label "depends-on:<ISSUE_NO>" --json number,labels

# Tum bagimliliklari cozulmus issue'lara status:ready ekle
for ISSUE in <dependent_issues>; do
  ALL_DEPS_RESOLVED=true
  for DEP in <issue_dependencies>; do
    if ! gh issue view $DEP --json labels | grep -q "status:merged"; then
      ALL_DEPS_RESOLVED=false
      break
    fi
  done
  if [ "$ALL_DEPS_RESOLVED" = true ]; then
    gh issue edit $ISSUE --add-label "status:ready"
  fi
done
```

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
