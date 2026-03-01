# /feature-branch

> Feature branch olusturma komutu.

## Kullanim

```
/feature-branch <FAZ> <ISSUE_NO> <ACIKLAMA>
```

**Parametreler**:
- `FAZ`: Faz numarasi (1, 2, 3, ...)
- `ISSUE_NO`: GitHub issue numarasi
- `ACIKLAMA`: Branch aciklamasi (bosluklu, slug'a cevirilecek)

**Ornekler**:
```
/feature-branch 1 42 Chat ekrani websocket baglantisi
/feature-branch 2 15 Sesli komut entegrasyonu
/feature-branch 1 7 Auth JWT token
```

## Branch Format

```
feature/f<FAZ>/<ISSUE_NO>-<slug>
```

Ornekler:
```
feature/f1/42-chat-ekrani-websocket-baglantisi
feature/f2/15-sesli-komut-entegrasyonu
feature/f1/7-auth-jwt-token
```

## Calisma Adimlari

### Adim 1: Slug Olusturma

Aciklama metnini slug formatina cevir:
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

### Adim 2: Develop Branch'ini Guncelle

```bash
# Uncommitted changes varsa stash yap
git stash

# Remote'u fetch et
git fetch origin

# develop branch'ine gec
git checkout develop

# Pull ile guncelle
git pull origin develop
```

Eger develop branch'i yoksa:
```bash
# origin/develop varsa ondan olustur
git checkout -b develop origin/develop

# origin/develop da yoksa origin/main'den olustur
git checkout -b develop origin/main
```

### Adim 3: Branch Var mi Kontrol Et

```bash
# Lokal branch kontrol
git branch --list "feature/f<FAZ>/<ISSUE_NO>-*"

# Remote branch kontrol
git ls-remote --heads origin "feature/f<FAZ>/<ISSUE_NO>-*"
```

Mevcut branch varsa: uyari goster ve mevcut branch'e gec (`git checkout <branch>`).

### Adim 4: Branch Olustur

```bash
BRANCH_NAME="feature/f<FAZ>/<ISSUE_NO>-<slug>"
git checkout -b "$BRANCH_NAME"

# Stash varsa geri yukle
git stash pop 2>/dev/null || true
```

### Adim 5: Dogrulama

```bash
# Mevcut branch'i dogrula
git branch --show-current
# Beklenen: feature/f<FAZ>/<ISSUE_NO>-<slug>

# develop'dan ayrildiqini dogrula
git log --oneline develop..HEAD
# Beklenen: 0 commit (henuz yeni)
```

## Cikti

```
Feature Branch Olusturuldu
==========================
Branch: feature/f<FAZ>/<ISSUE_NO>-<slug>
Base: develop (commit: <short-hash>)
Issue: #<ISSUE_NO>
Faz: F<FAZ>

Sonraki adimlar:
  1. Kod degisikliklerini yapin
  2. git add && git commit
  3. /create-pr ile PR olusturun
```

## Hata Yonetimi

| Hata | Aksiyon |
|------|---------|
| develop branch'i yok | `origin/develop`'dan olustur. O da yoksa `origin/main`'den olustur |
| Uncommitted changes var | `git stash` yap, branch olustur, `git stash pop` uygula |
| Branch zaten var | Uyari goster, mevcut branch'e gec (`git checkout <branch>`) |
| Git repo degil | Hata mesaji, cik |
| Remote erisim hatasi | `git fetch` hatasini goster |

## Issue Entegrasyonu

Issue numarasi verilmisse, issue metadata'sini da kontrol et:

```bash
gh issue view <ISSUE_NO> --json title,labels,state --repo atknatk/rafraf
```

- Issue kapali mi? -> Uyari goster
- Issue `status:merged` mi? -> Hata, bu issue zaten tamamlanmis
- Issue `status:blocked` mi? -> Uyari, bu issue engelli durumda
