# AI Project Supervisor — Testing Strategy (Web & Mobile)

**Document 6/8** | Version 1.0 | March 2026

---

## 1. Genel Bakis

Test katmani, AI Supervisor'un "gozleri"dir. Web projelerini Playwright ile, mobil projeleri Maestro ile test eder, screenshot alir ve sonuclari kullaniciya raporlar. Bu dokuman her iki test aracinin detayli konfigurasyonunu, test senaryolarini ve entegrasyon yaklasimini tanimlar.

---

## 2. Web Test: Playwright (Chrome-Only)

### 2.1 Neden Playwright?

- MCP Server destegi: Claude dogrudan Playwright'i tool olarak kullanabilir
- Chrome-only mod: Tek browser, dusuk kaynak tuketimi
- Screenshot ve video kaydi: AI'in "gormesi" icin
- Network interception: API cagrilarini izleme
- Mobile emulation: Responsive test
- Auto-wait: Element'lerin yuklenmesini otomatik bekler
- Microsoft destekli, aktif gelistirme

### 2.2 Kurulum ve Konfigürasyon

**Python Paketi:**
```bash
pip install playwright
playwright install chromium  # Sadece Chrome
```

**Base Konfigürasyon:**
```python
# playwright_config.py

PLAYWRIGHT_CONFIG = {
    "browser": "chromium",
    "launch_options": {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",  # Docker uyumu
            "--disable-gpu"
        ]
    },
    "context_options": {
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
        "locale": "tr-TR",
        "timezone_id": "Europe/Istanbul"
    },
    "timeouts": {
        "navigation": 30000,    # 30 saniye
        "action": 10000,        # 10 saniye
        "expect": 5000          # 5 saniye
    },
    "screenshot": {
        "type": "png",
        "full_page": False,
        "quality": None         # PNG icin N/A
    },
    "output_dirs": {
        "screenshots": "/tmp/playwright/screenshots/",
        "videos": "/tmp/playwright/videos/",
        "traces": "/tmp/playwright/traces/"
    }
}
```

### 2.3 Proje Bazli Konfigürasyon

Her projenin kendi Playwright konfigurasyonu vardir:

```yaml
# projects.yaml icinde
projects:
  - slug: project-x
    playwright:
      base_url: "http://localhost:3000"
      auth:
        type: "form"
        login_url: "/login"
        username_selector: "#email"
        password_selector: "#password"
        submit_selector: "button[type='submit']"
        test_credentials:
          username: "test@example.com"
          password: "test123"
        success_indicator: "/dashboard"
      critical_pages:
        - name: "Ana Sayfa"
          url: "/"
          expected_elements: ["nav", "h1", "footer"]
        - name: "Dashboard"
          url: "/dashboard"
          requires_auth: true
          expected_elements: [".stats-card", ".chart-container"]
        - name: "Profil"
          url: "/profile"
          requires_auth: true
      api_patterns:
        - "/api/v1/*"
        - "/graphql"
```

### 2.4 Test Senaryolari

**Senaryo 1: Sayfa Yuklenme Kontrolu**
```python
async def check_page_load(project_config, url):
    """Sayfanin duzgun yuklenip yuklenmedigini kontrol eder."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(**config["launch_options"])
        context = await browser.new_context(**config["context_options"])
        page = await context.new_page()

        # Performance metrikleri topla
        metrics = {}
        start_time = time.time()

        response = await page.goto(url, wait_until="networkidle")
        metrics["load_time"] = time.time() - start_time
        metrics["status_code"] = response.status
        metrics["title"] = await page.title()

        # Console hatalari kontrol et
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # Screenshot al
        screenshot = await page.screenshot()
        screenshot_url = await upload_to_s3(screenshot, f"screenshots/{project_slug}/{url_slug}.png")

        await browser.close()

        return {
            "success": response.status == 200 and not console_errors,
            "metrics": metrics,
            "console_errors": console_errors,
            "screenshot_url": screenshot_url
        }
```

**Senaryo 2: Login Akisi Testi**
```python
async def test_login_flow(project_config):
    """Login akisinin calisip calismadigini test eder."""
    auth = project_config["auth"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(**config["launch_options"])
        page = await browser.new_page()

        # Login sayfasina git
        await page.goto(f"{base_url}{auth['login_url']}")
        await page.screenshot(path="login_page.png")

        # Formu doldur
        await page.fill(auth["username_selector"], auth["test_credentials"]["username"])
        await page.fill(auth["password_selector"], auth["test_credentials"]["password"])

        # Submit
        await page.click(auth["submit_selector"])
        await page.wait_for_url(f"**{auth['success_indicator']}**", timeout=10000)

        # Basarili mi?
        current_url = page.url
        success = auth["success_indicator"] in current_url
        await page.screenshot(path="after_login.png")

        await browser.close()

        return {
            "success": success,
            "final_url": current_url,
            "screenshots": ["login_page.png", "after_login.png"]
        }
```

**Senaryo 3: API Izleme (Network Interception)**
```python
async def monitor_api_calls(project_config, url, duration=10):
    """Sayfa yuklenirken yapilan API cagrilarini izler."""
    api_calls = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(**config["launch_options"])
        page = await browser.new_page()

        # Network isteklerini yakala
        async def handle_request(route, request):
            api_calls.append({
                "url": request.url,
                "method": request.method,
                "headers": dict(request.headers),
                "timestamp": time.time()
            })
            await route.continue_()

        for pattern in project_config["api_patterns"]:
            await page.route(f"**{pattern}", handle_request)

        await page.goto(f"{base_url}{url}", wait_until="networkidle")

        # Response'lari da yakala
        api_responses = []
        page.on("response", lambda res: api_responses.append({
            "url": res.url,
            "status": res.status,
            "timing": res.timing
        }))

        await browser.close()

        return {
            "total_api_calls": len(api_calls),
            "calls": api_calls,
            "responses": api_responses,
            "failed_calls": [r for r in api_responses if r["status"] >= 400]
        }
```

**Senaryo 4: Responsive Test**
```python
async def check_responsive(project_config, url):
    """Farkli ekran boyutlarinda test eder."""
    viewports = [
        {"name": "desktop", "width": 1920, "height": 1080},
        {"name": "tablet", "width": 768, "height": 1024},
        {"name": "mobile", "width": 375, "height": 812},
    ]

    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(**config["launch_options"])

        for vp in viewports:
            context = await browser.new_context(viewport={"width": vp["width"], "height": vp["height"]})
            page = await context.new_page()
            await page.goto(f"{base_url}{url}", wait_until="networkidle")

            screenshot = await page.screenshot(full_page=True)
            screenshot_url = await upload_to_s3(screenshot, f"responsive/{vp['name']}.png")

            results.append({
                "viewport": vp["name"],
                "resolution": f"{vp['width']}x{vp['height']}",
                "screenshot_url": screenshot_url,
                "console_errors": []
            })
            await context.close()

        await browser.close()

    return {"viewports_tested": len(results), "results": results}
```

**Senaryo 5: Kirik Link Kontrolu**
```python
async def check_broken_links(project_config, url):
    """Sayfadaki tum linkleri kontrol eder."""
    broken_links = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(**config["launch_options"])
        page = await browser.new_page()
        await page.goto(f"{base_url}{url}", wait_until="networkidle")

        # Tum linkleri topla
        links = await page.eval_on_selector_all("a[href]", "els => els.map(el => el.href)")

        for link in links:
            try:
                response = await page.request.get(link)
                if response.status >= 400:
                    broken_links.append({"url": link, "status": response.status})
            except Exception as e:
                broken_links.append({"url": link, "error": str(e)})

        await browser.close()

    return {
        "total_links": len(links),
        "broken_count": len(broken_links),
        "broken_links": broken_links
    }
```

**Senaryo 6: Visual Regression (Gorsel Karsilastirma)**
```python
async def visual_compare(project_config, url, baseline_s3_key):
    """Mevcut gorunumu baseline screenshot ile karsilastirir."""
    # Baseline indir
    baseline = await download_from_s3(baseline_s3_key)

    # Yeni screenshot al
    async with async_playwright() as p:
        browser = await p.chromium.launch(**config["launch_options"])
        page = await browser.new_page()
        await page.goto(f"{base_url}{url}", wait_until="networkidle")
        current = await page.screenshot()
        await browser.close()

    # Pixel-by-pixel karsilastirma (pixelmatch veya Pillow ile)
    diff_percentage = calculate_diff(baseline, current)

    return {
        "baseline_url": baseline_s3_key,
        "current_screenshot": current_s3_url,
        "diff_percentage": diff_percentage,
        "changed": diff_percentage > 0.5,  # %0.5'ten fazla fark varsa
        "diff_image_url": diff_image_s3_url
    }
```

### 2.5 Playwright Docker Konfigurasyonu

```dockerfile
# Tool runner Dockerfile icinde
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Sadece Chromium (Firefox, WebKit gereksiz)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium

# Gerekli Python paketleri
COPY requirements.txt .
RUN pip install -r requirements.txt
```

---

## 3. Mobil Test: Maestro

### 3.1 Neden Maestro?

- YAML tabanli: AI'in test olusturmasi ve okumasi cok kolay
- iOS + Android: Her iki platform tek aracla
- Hizli: Appium'dan 5-10x daha hizli
- Kurulumu basit: Tek CLI, bagimliligi az
- Screenshot destegi: Built-in
- Native app destegi: Swift ve Kotlin/Java uygulamalari test edebilir

### 3.2 Kurulum

```bash
# macOS / Linux
curl -Ls "https://get.maestro.mobile.dev" | bash

# Dogrulama
maestro --version
```

### 3.3 Proje Bazli Konfigürasyon

```yaml
# projects.yaml icinde
projects:
  - slug: project-x
    maestro:
      ios:
        app_id: "com.company.projectx"
        app_path: "./build/ios/ProjectX.app"
        device: "iPhone 15 Pro"
      android:
        app_id: "com.company.projectx"
        apk_path: "./build/android/app-debug.apk"
        device: "Pixel 7"
      flows_dir: "./maestro/flows/"
      screenshots_dir: "/tmp/maestro/screenshots/"
```

### 3.4 Test Flow'lari

**Flow 1: Uygulama Baslatma ve Ana Ekran**
```yaml
# flows/01_app_launch.yaml
appId: com.company.projectx
---
- launchApp
- assertVisible: "Hosgeldiniz"
- takeScreenshot: "app_launch"
- assertVisible:
    id: "main_navigation"
```

**Flow 2: Login Akisi**
```yaml
# flows/02_login.yaml
appId: com.company.projectx
---
- launchApp
- tapOn: "Giris Yap"
- assertVisible: "E-posta"
- inputText:
    id: "email_input"
    text: "test@example.com"
- inputText:
    id: "password_input"
    text: "test123"
- takeScreenshot: "login_filled"
- tapOn: "Giris"
- assertVisible: "Ana Sayfa"
- takeScreenshot: "login_success"
```

**Flow 3: Navigasyon Testi**
```yaml
# flows/03_navigation.yaml
appId: com.company.projectx
---
- launchApp
# Login (onceki flow'dan)
- runFlow: "02_login.yaml"

# Tab bar navigasyonu
- tapOn: "Profil"
- assertVisible: "Profil Bilgileri"
- takeScreenshot: "profile_page"

- tapOn: "Ayarlar"
- assertVisible: "Uygulama Ayarlari"
- takeScreenshot: "settings_page"

- tapOn: "Ana Sayfa"
- assertVisible: "Ana Sayfa"
- takeScreenshot: "home_page"
```

**Flow 4: Form Submit Testi**
```yaml
# flows/04_form_submit.yaml
appId: com.company.projectx
---
- launchApp
- runFlow: "02_login.yaml"

- tapOn: "Yeni Gonderi"
- inputText:
    id: "title_input"
    text: "Test Gonderisi"
- inputText:
    id: "content_input"
    text: "Bu bir test icerigidir."
- takeScreenshot: "form_filled"
- tapOn: "Gonder"
- assertVisible: "Gonderi basariyla olusturuldu"
- takeScreenshot: "form_success"
```

**Flow 5: Hata Durumu Testi**
```yaml
# flows/05_error_handling.yaml
appId: com.company.projectx
---
- launchApp
- tapOn: "Giris Yap"
- inputText:
    id: "email_input"
    text: "wrong@email.com"
- inputText:
    id: "password_input"
    text: "wrongpassword"
- tapOn: "Giris"
- assertVisible: "Hatali e-posta veya sifre"
- takeScreenshot: "login_error"
```

**Flow 6: Scroll ve Liste Testi**
```yaml
# flows/06_scroll_list.yaml
appId: com.company.projectx
---
- launchApp
- runFlow: "02_login.yaml"

- tapOn: "Listeler"
- assertVisible: "Ogelerin Listesi"
- scroll:
    direction: DOWN
    duration: 2000
- takeScreenshot: "list_scrolled"
- scroll:
    direction: UP
    duration: 2000
```

### 3.5 AI Tarafindan Flow Olusturma

AI, kullanici istegine gore dinamik Maestro flow'lari olusturabilir:

```python
async def generate_maestro_flow(project_config, platform, description):
    """
    Kullanici açiklamasi: "Login ekranini test et, yanlis sifre ile dene"
    AI bu aciklamadan Maestro YAML olusturur.
    """
    prompt = f"""
    Asagidaki test senaryosu icin Maestro YAML flow olustur:
    Platform: {platform}
    App ID: {project_config['maestro'][platform]['app_id']}
    Senaryo: {description}

    Kurallar:
    - Turkce etiketler kullan
    - Her onemli adimda takeScreenshot ekle
    - assertVisible ile dogrulama yap
    - Hata durumlarini da kontrol et
    """

    # Claude API ile flow olustur
    flow_yaml = await generate_with_claude(prompt)

    # Dosyaya kaydet
    flow_path = f"flows/generated_{timestamp}.yaml"
    save_flow(flow_path, flow_yaml)

    return flow_path
```

### 3.6 Maestro Calistirma ve Sonuc Toplama

```python
async def run_maestro_flow(project_config, platform, flow_file):
    """Maestro flow calistirir ve sonuclari toplar."""
    app_config = project_config["maestro"][platform]

    command = f"maestro test {flow_file} --platform {platform}"
    if platform == "ios":
        command += f" --device '{app_config['device']}'"

    result = await run_shell_command(command, timeout=120)

    # Screenshot'lari topla ve S3'e yukle
    screenshots = glob.glob(f"{config['screenshots_dir']}/*.png")
    screenshot_urls = []
    for ss in screenshots:
        url = await upload_to_s3(ss, f"maestro/{project_slug}/{platform}/{os.path.basename(ss)}")
        screenshot_urls.append(url)

    return {
        "success": result.returncode == 0,
        "output": result.stdout,
        "errors": result.stderr,
        "screenshots": screenshot_urls,
        "duration_seconds": result.duration
    }
```

### 3.7 Maestro Docker / CI Konfigurasyonu

Maestro iOS testleri macOS gerektirir (simulator icin). Android testleri Linux'ta calisabilir.

**Android (EKS'te calisabilir):**
```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y openjdk-17-jdk android-sdk
# Maestro kurulumu
RUN curl -Ls "https://get.maestro.mobile.dev" | bash
# Android emulator
RUN sdkmanager "emulator" "system-images;android-34;google_apis;x86_64"
```

**iOS (macOS runner gerekli):**
- GitHub Actions macOS runner kullanilabilir
- Veya dedicated Mac Mini / Mac Studio
- XCode + Simulator kurulu olmali

---

## 4. Test Calistirma Stratejisi

### 4.1 On-Demand (Kullanici Istegi ile)

```
Kullanici: "Proje X'in ana sayfasini test et"
→ AI: Playwright ile ana sayfayi acar, screenshot alir, hatalari kontrol eder
→ Sonuc: Screenshot + hata raporu
```

### 4.2 Otomatik (Tool Sonrasi)

```
AI: Docker compose up calistirdi
→ Otomatik: Health check + ana sayfa screenshot
→ Sonuc: Servisler saglikli, site erisileabilir

AI: Git pull yapti (yeni kod geldi)
→ Otomatik: Test suite calistir
→ Sonuc: 45/47 test gecti, 2 fail → kullaniciya bildir
```

### 4.3 Periyodik (Faz 6 - Proaktif)

```
Her 6 saatte bir:
→ Tum production projelerin health check
→ Ana sayfa screenshot (visual regression)
→ API endpoint'lerin response time
→ Degisiklik varsa kullaniciya push notification
```

---

## 5. Test Sonuc Formati

Tum test sonuclari standart bir formatta raporlanir:

```json
{
  "test_id": "test_uuid",
  "project_slug": "project-x",
  "test_type": "web_page_load",
  "tool": "playwright",
  "timestamp": "2026-03-01T10:30:00Z",
  "duration_seconds": 3.5,
  "success": true,
  "summary": "Ana sayfa basariyla yuklendi. Yuklenme suresi 1.2 saniye. Hata yok.",
  "details": {
    "url": "http://localhost:3000",
    "status_code": 200,
    "load_time_ms": 1200,
    "console_errors": [],
    "network_errors": []
  },
  "screenshots": [
    {
      "name": "ana_sayfa",
      "url": "s3://bucket/screenshots/project-x/ana_sayfa.png",
      "timestamp": "2026-03-01T10:30:02Z"
    }
  ],
  "metrics": {
    "dom_content_loaded": 800,
    "first_paint": 400,
    "largest_contentful_paint": 1100,
    "total_requests": 23,
    "total_transfer_size_kb": 450
  }
}
```

---

## 6. Hata Siniflandirmasi

| Hata Tipi | Ciddiyet | Ornek | AI Aksiyonu |
|-----------|----------|-------|-------------|
| Site erisileamiyor | Kritik | Connection refused | Kullaniciya hemen bildir |
| 500 Server Error | Yuksek | Internal server error | Docker log kontrol et |
| Test fail | Yuksek | Beklenen element bulunamadi | Detay ile bildir |
| Yavas yukleme | Orta | > 5 saniye | Uyari olarak bildir |
| Console error | Dusuk | JS hatasi | Raporla, acil degil |
| Visual degisiklik | Bilgi | CSS degisikligi | Screenshot ile goster |

---

*Bu dokuman AI Project Supervisor serisinin 6/8 numarali dokumanidir.*
*Onceki: 05_Memory_System_Specification.md*
*Sonraki: 07_Security_Permissions_Cost_Analysis.md*
