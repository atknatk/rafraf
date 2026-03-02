# Feature: Playwright Runner (Screenshot, Page Load)

**Issue**: #15
**Faz**: F2
**Katmanlar**: agent
**Pipeline**: full
**Tarih**: 2026-03-02

## Ozet

Playwright async API kullanarak web sayfasi islemleri gerceklestiren runner. Sayfa yukleme,
screenshot alma (full page ve element bazli), element varlik kontrolu, form doldurma,
network response bekleme ve screenshot'lari S3'e yukleme yeteneklerini saglar.
Host Agent'in browser otomasyonu kabiliyetini aktif hale getirir.

## Degisecek Dosyalar

### Agent (`apps/agent/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `agent/runners/playwright_runner.py` | CREATE | Playwright runner implementasyonu |
| `agent/upload/__init__.py` | CREATE | Upload modulu init |
| `agent/upload/s3_uploader.py` | CREATE | Screenshot S3 upload yardimcisi |

## API Endpoints

Bu feature yeni REST endpoint veya WebSocket mesaj tipi eklememektedir.
Playwright runner, mevcut `agent_command` mesaj akisi uzerinden tetiklenir.
Backend'den gelen `tool: "playwright"` komutlari runner'a yonlendirilir.

## WebSocket Messages

Mevcut `agent_command` / `agent_command_result` mesajlari kullanilir. Yeni mesaj tipi yoktur.

### Playwright Komut Parametreleri (agent_command icinde)

| Action | Params | Aciklama |
|--------|--------|----------|
| `take_screenshot` | `url`, `full_page?`, `selector?`, `viewport?` | Sayfa veya element screenshot'i |
| `check_page_load` | `url`, `wait_until?`, `timeout?` | Sayfa yuklenme kontrolu |
| `check_element` | `url`, `selector`, `timeout?` | Element varlik kontrolu |
| `fill_form` | `url`, `fields[]`, `submit_selector?` | Form doldurma |
| `wait_for_response` | `url`, `url_pattern`, `timeout?` | Network response bekleme |

## Data Model

### Pydantic Models (Agent)

```python
class ScreenshotParams(BaseModel):
    model_config = ConfigDict(frozen=True)
    url: str
    full_page: bool = False
    selector: str | None = None
    viewport_width: int = 1920
    viewport_height: int = 1080

class PageLoadParams(BaseModel):
    model_config = ConfigDict(frozen=True)
    url: str
    wait_until: str = "load"  # "load", "domcontentloaded", "networkidle", "commit"
    timeout: int = 30

class ElementCheckParams(BaseModel):
    model_config = ConfigDict(frozen=True)
    url: str
    selector: str
    timeout: int = 10

class FormField(BaseModel):
    model_config = ConfigDict(frozen=True)
    selector: str
    value: str

class FillFormParams(BaseModel):
    model_config = ConfigDict(frozen=True)
    url: str
    fields: list[FormField]
    submit_selector: str | None = None

class WaitForResponseParams(BaseModel):
    model_config = ConfigDict(frozen=True)
    url: str
    url_pattern: str
    timeout: int = 30
```

## Business Rules

1. Playwright her zaman headless Chrome/Chromium kullanir
2. Varsayilan viewport: 1920x1080
3. Sayfa yukleme max timeout: 30 saniye
4. Screenshot formati: PNG
5. Screenshot'lar S3'e yuklenir, S3 URL'i sonucta dondurulur
6. S3 upload basarisiz olursa screenshot bytes base64 olarak dondurulur (fallback)
7. Browser instance her islemde acilip kapatilir (izolasyon)
8. Capability kontrolu: Agent config'de `capability_playwright=True` olmali
9. Bilinmeyen aksiyon icin ValueError firlatilir
10. Timeout durumlarinda uygun hata mesaji dondurulur

## Test Requirements

### Agent
- [ ] Unit test: take_screenshot basarili senaryo (playwright mock)
- [ ] Unit test: take_screenshot full_page ve element modlari
- [ ] Unit test: check_page_load basarili ve timeout senaryolari
- [ ] Unit test: check_element element bulundu ve bulunamadi senaryolari
- [ ] Unit test: fill_form basarili ve submit senaryolari
- [ ] Unit test: wait_for_response basarili ve timeout senaryolari
- [ ] Unit test: bilinmeyen aksiyon ValueError testi
- [ ] Unit test: S3 upload basarili ve fallback senaryolari
- [ ] Unit test: gecersiz URL handling
- [ ] Unit test: timeout handling tum aksiyonlar icin
- [ ] Integration test: Playwright browser acma/kapama

## Acceptance Criteria

- [ ] Sayfa yukleme (URL) calisiyor
- [ ] Screenshot alma (full page + element) calisiyor
- [ ] Element varlik kontrolu (selector) calisiyor
- [ ] Form doldurma calisiyor
- [ ] Network response bekleme calisiyor
- [ ] Screenshot'lari S3'e yukleme calisiyor
- [ ] Timeout handling dogru calisiyor
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
