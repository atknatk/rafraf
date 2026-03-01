# /verify

> Kod kalitesi ve test dogrulama komutu.

## Kullanim

```
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

## Dogrulama Adimlari

### Backend Dogrulama (`/verify backend` veya `/verify all`)

Asagidaki adimlari sirali olarak calistir. Her adimda basarisizlik durumunda hatayi raporla ama sonraki adima devam et.

#### 1. Ruff Lint

```bash
cd apps/backend && ruff check app/
```

Basarisizsa: Hatalari listele, duzeltme onerileri goster.

Auto-fix denemesi:
```bash
cd apps/backend && ruff check app/ --fix
```

#### 2. Ruff Format

```bash
cd apps/backend && ruff format --check app/
```

Basarisizsa: Formatlanmamis dosyalari listele.

#### 3. MyPy Type Check

```bash
cd apps/backend && mypy app/ --strict
```

Basarisizsa: Type hata listesi goster. Her hata icin dosya:satir:hata formati.

#### 4. Pytest + Coverage

```bash
cd apps/backend && python -m pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=80 -v
```

Basarisizsa: Basarisiz testleri ve coverage raporunu goster.

**Coverage esigi**: >= 80%

### iOS Dogrulama (`/verify ios` veya `/verify all`)

#### 1. SwiftLint

```bash
cd apps/ios && swiftlint
```

Basarisizsa: Lint hatalari listele (warning vs error ayir).

#### 2. Xcodebuild Build

```bash
cd apps/ios && xcodebuild build \
  -scheme RafRaf \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  -quiet
```

Basarisizsa: Build hatalari goster.

#### 3. Xcodebuild Test

```bash
cd apps/ios && xcodebuild test \
  -scheme RafRaf \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  -enableCodeCoverage YES \
  -quiet
```

Basarisizsa: Basarisiz testleri listele.

**Coverage esigi**: >= 70%

### Agent Dogrulama (`/verify agent` veya `/verify all`)

#### 1. Ruff Lint

```bash
cd apps/agent && ruff check agent/
```

#### 2. Ruff Format

```bash
cd apps/agent && ruff format --check agent/
```

#### 3. MyPy Type Check

```bash
cd apps/agent && mypy agent/ --strict
```

#### 4. Pytest + Coverage

```bash
cd apps/agent && python -m pytest tests/ --cov=agent --cov-report=term-missing --cov-fail-under=80 -v
```

**Coverage esigi**: >= 80%

### Sadece Test (`/verify test`)

Tum katmanlarin testlerini calistir (lint/type check olmadan):

```bash
# Backend testleri
cd apps/backend && python -m pytest tests/ --cov=app --cov-report=term-missing -v

# iOS testleri
cd apps/ios && xcodebuild test \
  -scheme RafRaf \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  -enableCodeCoverage YES \
  -quiet

# Agent testleri
cd apps/agent && python -m pytest tests/ --cov=agent --cov-report=term-missing -v
```

## Cikti Formati

Dogrulama tamamlaninca asagidaki ozet tabloyu goster:

```
Dogrulama Sonucu
================

Backend
-------
| Arac           | Durum | Detay                    |
|----------------|-------|--------------------------|
| ruff check     | PASS  | 0 hata                   |
| ruff format    | PASS  | Tum dosyalar formatli    |
| mypy strict    | PASS  | 0 type error             |
| pytest         | PASS  | 42 test, 0 fail          |
| coverage       | PASS  | 85% (esik: 80%)         |

iOS
---
| Arac           | Durum | Detay                    |
|----------------|-------|--------------------------|
| swiftlint      | PASS  | 0 error, 2 warning       |
| xcodebuild     | PASS  | Build basarili           |
| xcodebuild test| PASS  | 28 test, 0 fail          |
| coverage       | PASS  | 74% (esik: 70%)         |

Agent
-----
| Arac           | Durum | Detay                    |
|----------------|-------|--------------------------|
| ruff check     | PASS  | 0 hata                   |
| ruff format    | PASS  | Tum dosyalar formatli    |
| mypy strict    | PASS  | 0 type error             |
| pytest         | PASS  | 31 test, 0 fail          |
| coverage       | PASS  | 82% (esik: 80%)         |

Genel: BASARILI (15/15 kontrol gecti)
```

Basarisizlik durumunda:

```
Genel: BASARISIZ (12/15 kontrol gecti, 3 basarisiz)

Basarisiz Kontroller:
  1. [Backend] mypy strict: 3 type error
     - app/services/chat_service.py:45: Argument 1 has incompatible type "str"
     - app/services/chat_service.py:67: Missing return type annotation
     - app/models/user.py:12: Need type annotation for "metadata"

  2. [iOS] swiftlint: 1 error
     - RafRaf/Features/Chat/Presentation/Views/ChatView.swift:23: Force Unwrap Violation

  3. [Agent] coverage: 75% (esik: 80%)
     - agent/runners/docker_runner.py: 45% coverage (eksik)
     - agent/runners/shell_runner.py: 60% coverage (eksik)
```

## Ozel Davranislar

- `/verify all` calistirildiginda bir katmanda hata olsa bile diger katmanlara devam et
- Her kontrol icin gecen sureyi olc ve raporla
- Coverage raporunda en dusuk coverage'a sahip dosyalari goster
- SwiftLint warning'lari PASS sayilir, sadece error'lar FAIL
- Ruff auto-fix uygulanabilirse uygula ve tekrar kontrol et
- Eger bir katmanin kaynak dizini bossa (henuz kod yazilmadiysa) o katmani SKIP olarak raporla
