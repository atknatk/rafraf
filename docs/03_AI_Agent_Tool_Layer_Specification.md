# RafRaf — AI Agent & Tool Layer Specification

**Document 3/8** | Version 1.1 | March 2026

---

## 1. Genel Bakis

AI Agent katmani, Claude API uzerinden calisan ve tool-calling mekanizmasi ile gercek islemleri yapan beyin katmanidir. Claude Agent SDK kullanilarak implement edilir. Bu dokuman, agent'in nasil calistigini, tool tanimlarini, model secim stratejisini ve onay mekanizmasini detayli olarak tanimlar.

---

## 2. Agent Framework: Claude Agent SDK

### 2.1 Neden Claude Agent SDK?

- Anthropic'in resmi SDK'si, Claude API ile en iyi entegrasyon
- Native tool calling destegi (function calling)
- MCP (Model Context Protocol) destegi — Playwright MCP, GitHub MCP vb.
- Conversation management ve streaming built-in
- Python native — backend ekosistemi ile uyumlu

### 2.2 Agent Calisma Dongusu (Tool-Calling Loop)

```
1. Kullanici mesaji gelir
2. mem0'dan ilgili hafiza cekilir
3. System prompt + hafiza + mesaj + tool tanimlari hazirlanir
4. Claude API'a gonderilir
5. Claude cevap verir:
   a. Eger duz metin ise → kullaniciya ilet
   b. Eger tool_call ise → tool'u calistir
6. Tool sonucu Claude'a geri gonderilir
7. Claude yeni cevap verir (tekrar tool_call olabilir)
8. Adim 5-7 tekrarlanir (max 10 iterasyon)
9. Son cevap kullaniciya iletilir
10. Onemli bilgiler mem0'ya kaydedilir
```

### 2.3 Max Iteration Siniri

Sonsuz donguyu onlemek icin maksimum 10 tool-calling iterasyonu. Bu sinira ulasildignda Claude'a "Son cevabini ver" talimat verilir. Tipik bir islem 2-4 iterasyonda tamamlanir.

---

## 3. Model Secim Stratejisi

Maliyet optimizasyonu icin iki model kullanilir:

### 3.1 Model Router Mantigi

| Islem Tipi | Model | Sebep |
|------------|-------|-------|
| Durum sorgusu ("Proje X'in durumu ne?") | Haiku | Basit, hizli, ucuz |
| Log okuma ve ozet | Haiku | Metin isleme, dusuk karmasiklik |
| Docker start/stop | Haiku | Basit komut secimi |
| Kod review ve analiz | Sonnet | Derinlemesine anlama gerektirir |
| Bug teshisi | Sonnet | Karmasik muhakeme |
| Test sonucu analizi | Sonnet | Coklu veri noktasi degerlendirme |
| Karar gerektiren durumlar | Sonnet | Onay oncesi analiz |
| Proje planlama/oneri | Sonnet | Yaratici dusunme |

### 3.2 Otomatik Model Secimi

```python
# Model router pseudocode
def select_model(message: str, context: dict) -> str:
    # Anahtar kelime tabanli basit router
    simple_keywords = ["durum", "status", "log", "start", "stop", "restart", "list"]
    complex_keywords = ["review", "analiz", "neden", "debug", "plan", "oner", "test sonuc"]

    message_lower = message.lower()

    if any(kw in message_lower for kw in complex_keywords):
        return "claude-sonnet-4-5-20250929"

    if any(kw in message_lower for kw in simple_keywords):
        return "claude-haiku-4-5-20251001"

    # Default: Sonnet (guvenli taraf)
    return "claude-sonnet-4-5-20250929"
```

### 3.3 Kullanici Override

Kullanici "detayli analiz yap" veya "hizli cevap ver" diyerek model secimini override edebilir.

---

## 4. System Prompt

### 4.1 Base System Prompt

```
Sen bir AI Proje Yoneticisisin. Adin "Supervisor".

Gorevlerin:
- Kullanicinin yazilim projelerini izlemek ve yonetmek
- GitHub Issues takibi, kod durumu kontrolu
- Docker ile servisleri calistirmak ve test etmek
- Playwright ile web testleri, Maestro ile mobil testler yapmak
- Kod kalitesini degerlendirmek
- Sonuclari acik ve ozet sekilde raporlamak

Kurallar:
- Turkce iletisim kur, teknik terimleri Ingilizce kullanabilirsin
- Kisa ve oze cevaplar ver, gereksiz aciklama yapma
- Hata oldugunda ne oldugunu ve ne yapilabilecegini acikla
- Onay gerektiren islemleri MUTLAKA kullaniciya sor
- Asla onaysiz deploy, kubectl, aws cli delete/run komutlari calistirma
- Her islem sonucunu logla

Onay Gerektiren Islemler (MUTLAKA KULLANICIYA SOR):
- kubectl (tum komutlar)
- aws cli (ozellikle delete, terminate, update)
- docker push (registry'ye push)
- git push (remote'a push)
- Production ortamina herhangi bir deploy
- Veritabani uzerinde write/delete islemleri
- Dosya silme islemleri

Onaysiz Yapabileceklerin:
- git status, diff, log okuma
- docker compose up/down (development ortam)
- docker logs okuma
- Test calistirma (Playwright, Maestro)
- Screenshot alma
- GitHub issue okuma
- Kod analizi ve review
- Dosya okuma

Host Ortamlari:
Sen 3 farkli makineye erisebilirsin:
- macbook-pro: Yeni macOS, Xcode + iOS Simulator, Maestro iOS
- macbook-air: Eski macOS, Android SDK, Maestro Android
- ubuntu-dev: Ubuntu server, 7/24 acik, Node.js/Next.js projeleri

Her proje belirli bir host'a atanmistir. Komutu dogru host'a gonder.
Host offline ise fallback host'u kullan. O da yoksa kullaniciya bildir.
Hangi host'larin cevrimici oldugu sana context olarak verilir.
```

### 4.2 Dinamik Context (Her Mesajda Eklenir)

```
# Aktif Projeler ve Host Eslesmesi
{projects_yaml_content}

# Host Agent Durumlari
macbook-pro: online  (CPU: %23, RAM: %45, Disk: 118GB bos)
macbook-air: online  (CPU: %12, RAM: %38, Disk: 85GB bos)
ubuntu-dev:  online  (CPU: %8,  RAM: %22, Disk: 340GB bos, uptime: 45 gun)

# Kullanici Hafizasi (mem0)
{relevant_memories}

# Son Islem Gecmisi (son 5 islem)
{recent_audit_log}

# Mevcut Proje Durumu (eger belirli bir proje hakkinda konusuluyorsa)
{current_project_status}
```

---

## 5. Host-Aware Tool Dispatch (YENI)

Tool'lar iki kategoriye ayrilir: Cloud Tool'lar (EKS uzerinde) ve Host Tool'lar (agent uzerinde).

### 5.1 Tool Konum Matrisi

| Tool | Konum | Aciklama |
|------|-------|----------|
| github_manager | EKS (Cloud) | API-based, host gerekmez |
| file_manager (S3) | EKS (Cloud) | API-based, host gerekmez |
| memory_manager | EKS (Cloud) | mem0, host gerekmez |
| docker_manager | Host Agent | Projenin atandigi host'ta calisir |
| web_tester (Playwright) | Host Agent | Projenin calistigi host'ta calisir |
| mobile_tester_ios (Maestro) | macbook-pro ONLY | Xcode/Simulator gerekli |
| mobile_tester_android (Maestro) | macbook-air ONLY | Android SDK gerekli |
| shell_executor | Host Agent | Projenin atandigi host'ta calisir |

### 5.2 Dispatch Akisi

```python
async def dispatch_tool(tool_name: str, project_slug: str, params: dict):
    project = get_project(project_slug)

    # Cloud tool'lar dogrudan EKS'te calisir
    if tool_name in CLOUD_TOOLS:
        return await execute_cloud_tool(tool_name, params)

    # Host tool'lar icin dogru host'u bul
    target_host = project.primary_host_id
    agent = get_agent(target_host)

    if agent.status != "online":
        # Fallback host'u dene
        if project.fallback_host_id:
            fallback_agent = get_agent(project.fallback_host_id)
            if fallback_agent.status == "online":
                target_host = project.fallback_host_id
                agent = fallback_agent
            else:
                return error("Tum host'lar offline. Islem yapilamiyor.")
        else:
            return error(f"{target_host} offline ve fallback host tanimli degil.")

    # Ozel host gereksinimleri kontrol et
    if tool_name == "mobile_tester_ios" and target_host != "macbook-pro":
        return error("iOS testi sadece macbook-pro uzerinde yapilabilir.")
    if tool_name == "mobile_tester_android" and target_host != "macbook-air":
        return error("Android testi sadece macbook-air uzerinde yapilabilir.")

    # Komutu agent'a gonder
    return await send_command_to_agent(agent, tool_name, params)
```

### 5.3 Coklu Host Sorgulama

Kullanici "tum projelerin durumunu ver" dediginde:

```python
async def check_all_projects():
    results = []
    for project in get_all_active_projects():
        # Sirayla (paralel degil — token optimizasyonu)
        result = await dispatch_tool("health_check", project.slug, {})
        results.append(result)
        # Her sonuc aninda kullaniciya iletilir
        await send_to_user(format_status(project, result))
    return results
```

---

## 6. Tool Tanimlari

### 5.1 Docker Tool

**Tool Adi:** `docker_manager`

**Aciklama:** Docker container ve compose islemlerini yonetir.

**Fonksiyonlar:**

| Fonksiyon | Parametreler | Aciklama | Onay |
|-----------|-------------|----------|------|
| compose_up | project_slug, detached=true | Docker compose ile servisleri baslat | Hayir |
| compose_down | project_slug | Servisleri durdur | Hayir |
| compose_restart | project_slug, service_name? | Servisleri yeniden baslat | Hayir |
| compose_logs | project_slug, service_name?, tail=100 | Servis loglarini getir | Hayir |
| compose_ps | project_slug | Calislan container'lari listele | Hayir |
| container_stats | project_slug | CPU/memory kullanimi | Hayir |
| build | project_slug, no_cache=false | Docker image build et | Hayir |
| push | project_slug, tag | Image'i registry'ye push et | **EVET** |
| health_check | project_slug | Tum servislerin saglik durumu | Hayir |

**Ornek Tool Definition (Claude API formatinda):**

```json
{
  "name": "docker_manager",
  "description": "Docker container ve compose islemlerini yonetir. Development ortaminda compose up/down/restart/logs islemleri onaysiz yapilabilir. Registry'ye push islemi onay gerektirir.",
  "input_schema": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["compose_up", "compose_down", "compose_restart", "compose_logs", "compose_ps", "container_stats", "build", "push", "health_check"],
        "description": "Yapilacak Docker islemi"
      },
      "project_slug": {
        "type": "string",
        "description": "Proje slug'i (ornek: project-x)"
      },
      "service_name": {
        "type": "string",
        "description": "Opsiyonel: Belirli bir servis adi (ornek: web, api, db)"
      },
      "options": {
        "type": "object",
        "properties": {
          "detached": { "type": "boolean", "default": true },
          "no_cache": { "type": "boolean", "default": false },
          "tail": { "type": "integer", "default": 100 },
          "tag": { "type": "string" }
        }
      }
    },
    "required": ["action", "project_slug"]
  }
}
```

### 5.2 GitHub Tool

**Tool Adi:** `github_manager`

**Fonksiyonlar:**

| Fonksiyon | Parametreler | Aciklama | Onay |
|-----------|-------------|----------|------|
| list_issues | project_slug, state=open, labels? | Issue'lari listele | Hayir |
| get_issue | project_slug, issue_number | Issue detayi | Hayir |
| create_issue | project_slug, title, body, labels? | Yeni issue olustur | **EVET** |
| close_issue | project_slug, issue_number, comment? | Issue kapat | **EVET** |
| list_prs | project_slug, state=open | PR'lari listele | Hayir |
| get_pr | project_slug, pr_number | PR detayi ve diff | Hayir |
| review_pr | project_slug, pr_number | PR kod review analizi | Hayir |
| get_branch_diff | project_slug, branch | Branch degisikliklerini getir | Hayir |
| get_commit_history | project_slug, branch?, limit=10 | Son commit'leri listele | Hayir |
| get_actions_status | project_slug | GitHub Actions CI/CD durumu | Hayir |
| get_repo_stats | project_slug | Repo istatistikleri | Hayir |

### 5.3 Playwright Tool (Web Test)

**Tool Adi:** `web_tester`

**Calisma Modu:** Chrome-only (Chromium)

**Fonksiyonlar:**

| Fonksiyon | Parametreler | Aciklama | Onay |
|-----------|-------------|----------|------|
| take_screenshot | project_slug, url?, full_page=false | Ekran goruntusu al | Hayir |
| run_test_suite | project_slug | Tum Playwright testlerini calistir | Hayir |
| run_single_test | project_slug, test_file | Tek test dosyasi calistir | Hayir |
| check_page_load | project_slug, url | Sayfa yuklenme suresi ve hatalari | Hayir |
| check_links | project_slug, url | Kirik linkleri tespit et | Hayir |
| fill_form | project_slug, url, form_data | Form doldur ve submit et | Hayir |
| check_responsive | project_slug, url, viewports | Farkli ekran boyutlarinda test | Hayir |
| intercept_api | project_slug, url, api_pattern | API cagrilarini izle | Hayir |
| visual_compare | project_slug, url, baseline_screenshot | Gorsel karsilastirma | Hayir |
| accessibility_check | project_slug, url | Erisilebilirlik kontrolu | Hayir |

**Playwright Konfigurasyonu:**

```python
# Her proje icin Playwright context
playwright_config = {
    "browser": "chromium",
    "headless": True,
    "viewport": {"width": 1920, "height": 1080},
    "timeout": 30000,  # 30 saniye
    "screenshot_dir": "/tmp/screenshots/",
    "video_dir": "/tmp/videos/",
    "ignore_https_errors": True  # Development SSL icin
}
```

### 5.4 Maestro Tool (Mobil Test)

**Tool Adi:** `mobile_tester`

**Fonksiyonlar:**

| Fonksiyon | Parametreler | Aciklama | Onay |
|-----------|-------------|----------|------|
| run_flow | project_slug, platform, flow_file | Maestro flow calistir | Hayir |
| run_all_flows | project_slug, platform | Tum flow'lari calistir | Hayir |
| take_screenshot | project_slug, platform | Mobil ekran goruntusu | Hayir |
| check_app_launch | project_slug, platform | Uygulama baslatma testi | Hayir |
| generate_flow | project_slug, platform, description | AI ile Maestro flow olustur | Hayir |
| list_flows | project_slug | Mevcut flow'lari listele | Hayir |

**Platform Parametresi:** `ios` veya `android`

**Maestro Flow Ornegi (AI tarafindan olusturulabilir):**

```yaml
appId: com.company.projectx
---
- launchApp
- assertVisible: "Giris Yap"
- tapOn: "Giris Yap"
- inputText:
    id: "email_field"
    text: "test@example.com"
- inputText:
    id: "password_field"
    text: "test123"
- tapOn: "Giris"
- assertVisible: "Ana Sayfa"
- takeScreenshot: "login_success"
```

### 5.5 Shell Tool

**Tool Adi:** `shell_executor`

**Guvenlik:** En hassas tool. Komut whitelist'i ve blacklist'i uygulanir.

| Fonksiyon | Parametreler | Aciklama | Onay |
|-----------|-------------|----------|------|
| execute | command, timeout=60, cwd? | Shell komutu calistir | Degisir* |

**Onay Gerektiren Komutlar (Blacklist):**
```
kubectl *           → MUTLAKA ONAY
aws *               → MUTLAKA ONAY (ozellikle delete, terminate, update, run)
rm -rf *            → MUTLAKA ONAY
docker push *       → MUTLAKA ONAY
git push *          → MUTLAKA ONAY
npm publish *       → MUTLAKA ONAY
pip install *       → MUTLAKA ONAY (global)
systemctl *         → MUTLAKA ONAY
chmod *             → MUTLAKA ONAY
chown *             → MUTLAKA ONAY
```

**Onaysiz Calistirilabilenler (Whitelist):**
```
ls, cat, head, tail, grep, find, wc
git status, git log, git diff, git branch
docker ps, docker logs, docker stats
npm test, npm run lint, npm run build
python -m pytest, python -m pylint
curl (sadece GET), wget (sadece okuma)
df, du, free, top, ps
```

**Yasak Komutlar (ASLA Calistirilmaz):**
```
rm -rf /
mkfs *
dd if=/dev/zero *
:(){ :|:& };:      # Fork bomb
> /dev/sda
shutdown, reboot, halt
```

### 5.6 S3 File Tool

**Tool Adi:** `file_manager`

| Fonksiyon | Parametreler | Aciklama | Onay |
|-----------|-------------|----------|------|
| upload | local_path, s3_key | Dosya yukle | Hayir |
| download | s3_key, local_path | Dosya indir | Hayir |
| generate_url | s3_key, expiry=3600 | Pre-signed URL olustur | Hayir |
| list_files | prefix? | Dosyalari listele | Hayir |
| delete | s3_key | Dosya sil | **EVET** |

---

## 6. Onay Sistemi (Approval Mechanism)

### 6.1 Calisma Mantigi

```
1. Claude bir tool_call yapar
2. Tool registry'den onay gerekip gerekmedigi kontrol edilir
3. Onay gerekiyorsa:
   a. approval_requests tablosuna kayit olusturulur
   b. iOS app'e "question" tipi mesaj gonderilir
   c. Kullanici cevap verene kadar beklenir (timeout: 5 dakika)
   d. Onay gelirse tool calistirilir
   e. Red gelirse Claude'a "kullanici reddetti" bilgisi gonderilir
   f. Timeout olursa islem iptal edilir
4. Onay gerekmiyorsa tool dogrudan calistirilir
```

### 6.2 Onay Kategorileri

| Kategori | Ornekler | Timeout |
|----------|----------|---------|
| deploy | Production deploy, image push | 5 dakika |
| destructive | Dosya silme, DB drop, container remove | 5 dakika |
| infrastructure | kubectl, aws cli, systemctl | 5 dakika |
| write_remote | git push, issue create/close | 3 dakika |

### 6.3 Acil Durum Bypass

Acil durum bypass YOKTUR. Tum onay gerektiren islemler her zaman onay gerektirir. Bu bir guvenlik prensibidir ve degistirilemez.

---

## 7. Prompt Caching Stratejisi

Claude API'da prompt caching ile tekrar eden token'lar %90 indirimli olur.

### 7.1 Cache'lenecek Icerikler

| Icerik | Boyut (tahmini) | Degisim Sikligi |
|--------|-----------------|-----------------|
| System prompt | ~2000 token | Nadir (ayda 1) |
| Tool tanimlari | ~3000 token | Nadir (ayda 1) |
| Proje konfigurasyonu | ~1000 token | Haftada 1 |
| Kullanici hafizasi (mem0) | ~500-1000 token | Her konusmada |

### 7.2 Cache Uygulama

System prompt + tool tanimlari + proje config = ~6000 token sabit icerik. Bu her API call'da ayni oldugu icin cache'lenir. Tahmini tasarruf: aylik ~%30-40 maliyet azaltma.

---

## 8. Hata Yonetimi ve Recovery

### 8.1 Tool Hatasi Durumunda

```
1. Tool hata dondurur
2. Hata bilgisi Claude'a gonderilir
3. Claude hatayi analiz eder
4. Claude uc secenek arasinda karar verir:
   a. Retry: Ayni tool'u tekrar cagir (gecici hatalar icin)
   b. Alternative: Farkli bir yaklasim dene
   c. Report: Kullaniciya hatayi bildir ve oneri sun
```

### 8.2 Claude API Hatasi Durumunda

| Hata | Aksiyon |
|------|---------|
| 429 Rate Limit | Exponential backoff ile retry (1s, 2s, 4s) |
| 500 Server Error | 3 retry, basarisiz ise kullaniciya bildir |
| 529 Overloaded | 10 saniye bekle, retry |
| Timeout | Mesaji kisalt veya Haiku'ya fallback |

---

## 9. Loglama ve Observability

### 9.1 Log Seviyeleri

| Seviye | Kullanim |
|--------|----------|
| DEBUG | Tool input/output detaylari, Claude API tam response |
| INFO | Her tool call, her kullanici mesaji, session baslama/bitis |
| WARNING | Retry'lar, yavas response'lar, yuksek maliyet |
| ERROR | Tool hatalari, API hatalari, connection kayiplari |
| CRITICAL | Sistem cokmeleri, guvenlik ihlalleri |

### 9.2 Structured Log Formati

```json
{
  "timestamp": "2026-03-01T10:30:00.123Z",
  "level": "INFO",
  "service": "ai-orchestrator",
  "session_id": "session_uuid",
  "event": "tool_call",
  "tool": "docker_manager",
  "action": "compose_up",
  "project": "project-x",
  "duration_ms": 12500,
  "success": true,
  "tokens_used": { "input": 1500, "output": 200 },
  "model": "claude-haiku-4-5"
}
```

---

*Bu dokuman RafRaf serisinin 3/8 numarali dokumanidir.*
*Onceki: 02_Backend_API_WebSocket_Specification.md*
*Sonraki: 04_iOS_App_Specification.md*
