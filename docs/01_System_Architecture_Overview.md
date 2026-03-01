# RafRaf — System Architecture Overview

**Document 1/8** | Version 1.1 | March 2026

---

## 1. Proje Genel Bakis

RafRaf, birden fazla yazilim projesini es zamanli olarak izleyen, kod kalitesini degerlendiren, test eden ve raporlayan otonom bir AI asistan sistemidir. Sistem, bir iOS uygulamasi uzerinden sesli ve metin tabanli iletisim kurarak, kullanicinin projelerini 7/24 yonetmesine yardimci olur.

### 1.1 Temel Amac

Kullanicinin su an manuel olarak yaptigi proje yonetim islerini otomatize etmek:

- GitHub Issues takibi ve kod durumu kontrolu
- Docker ile servisleri calistirma ve saglilk kontrolu
- Playwright ile web testi ve screenshot alma
- Maestro ile iOS/Android mobil uygulama testi
- Kod kalitesi degerlendirmesi ve raporlama
- Sesli ve metin tabanli Turkce iletisim

### 1.2 Kapsam

- **Proje Sayisi:** 4-5 aktif proje (1 production, 3-4 AI-driven gelistirme)
- **Tech Stack:** Fullstack (Node.js, Python, Next.js) + Mobil (iOS Swift, Android Kotlin/Java)
- **Host Ortamlari:** 2 Mac (development) + 1 Ubuntu dev server + AWS EKS (backend)
- **Erisim:** 7/24, iOS uygulamasi uzerinden
- **Dil:** Turkce konusma input, Ingilizce kod analizi, Turkce raporlama

---

## 2. Yuksek Seviye Mimari

Sistem dort ana katmandan olusur: iOS Client, Backend (EKS), Host Agent'lar (Mac + Ubuntu) ve Cloud Tool'lar.

```
┌─────────────────────┐        WebSocket (WSS)        ┌────────────────────────────┐
│                     │  ◄──────────────────────────►  │                            │
│   iOS App (SwiftUI) │     ← text, voice, images →    │   Backend API (AWS EKS)    │
│                     │     ← questions, status →       │                            │
│   • Sesli input     │     ← progress updates →        │   ┌──────────────────────┐ │
│   • Sesli output    │                                 │   │  FastAPI WebSocket    │ │
│   • Rich UI         │                                 │   │  Server               │ │
│   • Interaktif Q&A  │                                 │   └──────────┬───────────┘ │
│   • Screenshot view │                                 │              │             │
│   • Dosya paylasim  │                                 │   ┌──────────▼───────────┐ │
│                     │                                 │   │  AI Orchestrator      │ │
└─────────────────────┘                                 │   │  (Claude Agent SDK)   │ │
                                                        │   └──────────┬───────────┘ │
                                                        │              │             │
                       ┌───────────────────────────────────────────────┘             │
                       │                                                │             │
          ┌────────────┼─────────────────────┐                          │             │
          │            │                     │                          │             │
          ▼            ▼                     ▼                          │             │
┌──────────────┐ ┌──────────────┐ ┌───────────────┐  ┌──────────────┐ │             │
│ Host Agent 1 │ │ Host Agent 2 │ │ Host Agent 3  │  │ Cloud Tools  │ │             │
│ "MacBook Pro"│ │ "MacBook Air"│ │ "Ubuntu Dev"  │  │ (EKS native) │ │             │
│ (Yeni macOS) │ │ (Eski macOS) │ │ (7/24 acik)   │  │              │ │             │
│              │ │              │ │               │  │ • GitHub API │ │             │
│ • Docker     │ │ • Docker     │ │ • Docker      │  │ • S3 Files   │ │             │
│ • Playwright │ │ • Playwright │ │ • Playwright  │  │ • mem0       │ │             │
│ • Maestro iOS│ │ • Maestro And│ │ • Shell       │  │ • CloudWatch │ │             │
│ • Shell      │ │ • Shell      │ │ • Node/Next   │  │              │ │             │
│ • Xcode/Swift│ │ • Android SDK│ │               │  │              │ │             │
└──────────────┘ └──────────────┘ └───────────────┘  └──────────────┘ │             │
       ▲                ▲                ▲                             │             │
       │                │                │                             │             │
       └────────────────┴────────────────┘                             │             │
                  WSS (Agent Protocol)                                 │             │
                                                        └─────────────────────────────┘

Dis Servisler:
  • Claude API (Anthropic) — AI reasoning & tool calling
  • Deepgram API — Speech-to-text (Turkce)
  • OpenAI TTS API — Text-to-speech (Turkce)
```

### 2.1 Katman 1: iOS Client (SwiftUI)

Native iOS uygulamasi. Kullanici ile AI arasindaki birincil arayuz.

**Sorumluluklar:**
- Sesli input alma ve Deepgram'a gonderme (STT)
- AI cevabini sesli olarak oynatma (TTS)
- WebSocket baglantisi yonetimi (reconnect, heartbeat)
- Interaktif soru-cevap UI (butonlar, secenekler)
- Screenshot ve gorsel gosterimi
- Proje durum kartlari
- Dosya upload/download (S3 uzerinden)
- Push notification (proaktif bildirimler icin)

### 2.2 Katman 2: Backend API (AWS EKS)

FastAPI tabanli WebSocket sunucusu. Tum is mantigi burada calisir.

**Sorumluluklar:**
- WebSocket baglanti yonetimi ve authentication (iOS + Host Agent'lar)
- Claude API ile tool-calling loop
- Host-aware tool dispatch (hangi komutu hangi host'a gonderecegini bilir)
- Memory management (mem0 entegrasyonu)
- Onay sistemi yonetimi (approval-required islemler)
- Session yonetimi ve conversation history
- Host Agent registry ve saglik izleme
- Maliyet takibi ve rate limiting
- Structured logging ve audit trail

### 2.3 Katman 3: Host Agent Layer (YENI)

Her fiziksel makinede (Mac veya Ubuntu) calisan hafif bir daemon servisi. Backend'e WSS ile baglanir ve yerel komutlari calistirir.

**3 Host Agent:**

| Host | Makine | OS | Ozel Yetenek | Projeler |
|------|--------|----|-------------|----------|
| macbook-pro | MacBook Pro (Yeni) | macOS 15+ | Xcode, iOS Simulator, Maestro iOS | iOS projeler + genel |
| macbook-air | MacBook Air (Eski) | macOS 14 | Android SDK, Maestro Android | Android projeler + genel |
| ubuntu-dev | Ubuntu Dev Server | Ubuntu 22.04 | 7/24 acik, yuksek kaynak | Node.js / Next.js projeleri |

**Host Agent Sorumluluklar:**
- Backend'e WSS ile baglanma ve kimlik dogrulama
- Yerel komut calistirma (Docker, Playwright, Maestro, Shell)
- Screenshot ve log dosyalarini S3'e yukleme
- Sistem kaynak bilgisi raporlama (CPU, RAM, disk)
- Heartbeat gondererek "cevrimici" durumunu bildirme
- Baglanti kopmasi durumunda otomatik reconnect

**Detayli spec: 08_Host_Agent_Specification.md**

### 2.4 Katman 4: Cloud Tool Layer (EKS Native)

Herhangi bir fiziksel makineye bagli olmayan, dogrudan EKS uzerinde calisan araclar.

| Tool | Kutuphane | Islem | Konum |
|------|-----------|-------|-------|
| GitHub Manager | PyGithub / GitHub API | Issue CRUD, PR review, branch analizi | EKS |
| File Manager | boto3 (AWS S3) | Dosya upload/download, pre-signed URL | EKS |
| Memory Manager | mem0 SDK | Hafiza okuma/yazma, fact extraction | EKS |
| Cost Tracker | Custom | API maliyet takibi | EKS |

### 2.5 Katman 5: Host-Specific Tool Layer

Fiziksel makine uzerinde calisan, host agent araciligiyla erisilebilen araclar.

| Tool | Kutuphane | Islem | Konum |
|------|-----------|-------|-------|
| Docker Manager | Docker SDK (Python) | Container start/stop/logs/build, compose up/down | Host Agent |
| Web Tester | Playwright (Chrome-only) | Site acma, screenshot, form test, network intercept | Host Agent |
| Mobile Tester (iOS) | Maestro CLI | iOS uygulama testi, screenshot, flow test | macbook-pro ONLY |
| Mobile Tester (Android) | Maestro CLI | Android uygulama testi | macbook-air ONLY |
| Shell Executor | subprocess (Python) | Genel komut calistirma (guvenlik filtreleri ile) | Host Agent |

---

## 3. Teknoloji Stack (Detayli)

### 3.1 Core Teknolojiler

| Katman | Teknoloji | Versiyon | Neden Secildi |
|--------|-----------|----------|---------------|
| AI Engine | Claude API (Sonnet + Haiku) | Latest | Native tool calling, Turkce destek, maliyet optimizasyonu |
| Agent Framework | Claude Agent SDK (Python) | Latest | MCP destegi, native Claude entegrasyonu |
| Backend Framework | FastAPI | 0.100+ | Async WebSocket, type-safe, Python ekosistemi |
| iOS App | SwiftUI | iOS 17+ | Native performans, modern deklaratif UI |
| Database | PostgreSQL + pgvector | 16+ | Memory storage, vector search, audit log |
| Memory | mem0 | Latest | Otomatik fact extraction, conversation memory |
| Container Orchestration | AWS EKS | 1.28+ | Mevcut altyapi |

### 3.2 Dis Servisler

| Servis | Saglayici | Kullanim |
|--------|-----------|----------|
| Speech-to-Text | Deepgram | Real-time streaming STT, Turkce |
| Text-to-Speech | OpenAI TTS | Turkce ses sentezi |
| Version Control | GitHub API | Issue, PR, repo yonetimi |
| File Storage | AWS S3 | Screenshot, dosya paylasimi |
| Monitoring | AWS CloudWatch | Log, metrik, alert |

### 3.3 Test Araclari

| Arac | Hedef | Kullanim |
|------|-------|----------|
| Playwright | Web (Chrome) | UI test, screenshot, API intercept |
| Maestro | iOS + Android | Mobil uygulama testi, YAML tabanli |

---

## 4. Veri Akisi

### 4.1 Standart Komut Akisi

```
Kullanici (Turkce ses)
    │
    ▼
iOS App: Deepgram STT ile metne cevir
    │
    ▼
WebSocket: Metin mesaji backend'e gonder
    │
    ▼
Backend: mem0'dan ilgili hafizayi cek
    │
    ▼
Backend: Claude API'a gonder (mesaj + hafiza + tool tanimlari)
    │
    ▼
Claude: Hangi tool'u cagiracagina karar ver
    │
    ▼
Backend: Tool'u calistir (Docker, Playwright, GitHub vb.)
    │
    ▼
Backend: Tool sonucunu Claude'a geri gonder
    │
    ▼
Claude: Kullaniciya ozet olustur
    │
    ▼
Backend: Yeni bilgileri mem0'ya kaydet
    │
    ▼
WebSocket: Sonucu iOS app'e gonder (metin + gorseller)
    │
    ▼
iOS App: OpenAI TTS ile sesli cevap olustur ve oynat
    │
    ▼
Kullanici gorsel + sesli cevap alir
```

### 4.2 Onay Gerektiren Akis

```
Claude: "Bu islem onay gerektiriyor" (deploy, kubectl, aws delete vb.)
    │
    ▼
Backend: iOS app'e "question" tipi mesaj gonder
    │
    ▼
iOS App: Interaktif butonlar goster
    ┌─────────────────────────────────┐
    │  Proje X'i production'a deploy  │
    │  etmek istiyor musunuz?         │
    │                                 │
    │  [Onayla]  [Reddet]  [Detay]    │
    └─────────────────────────────────┘
    │
    ▼
Kullanici buton tiklar veya sesle cevaplar
    │
    ▼
Backend: Onay → islemi calistir / Red → iptal et
```

### 4.3 Proaktif Bildirim Akisi (Faz 6)

```
GitHub Webhook: Yeni issue acildi / CI fail
    │
    ▼
Backend: Olayi degerlendir
    │
    ▼
Backend: Push notification gonder (iOS)
    │
    ▼
Kullanici bildirime tiklar → uygulama acilir → detay gosterilir
```

---

## 5. EKS Altyapi Yapisi

### 5.1 EKS Pod Konfigurasyonu

| Pod | Image | Replicas | CPU/Memory | Aciklama |
|-----|-------|----------|------------|----------|
| api-gateway | custom/api-gateway | 2 | 0.5 CPU / 512MB | WebSocket server (iOS + Host Agent), auth, routing |
| ai-orchestrator | custom/ai-orchestrator | 1 | 1 CPU / 1GB | Claude API, tool calling loop, host dispatch |
| agent-registry | custom/agent-registry | 1 | 0.25 CPU / 256MB | Host Agent kayit, saglik izleme, routing |
| mem0-server | mem0/mem0 | 1 | 0.5 CPU / 512MB | Memory management API |
| postgres | postgres:16-pgvector | 1 | 0.5 CPU / 1GB | Memory DB, audit log, session store |
| redis | redis:7-alpine | 1 | 0.25 CPU / 256MB | WebSocket session cache, rate limiting |

Not: `tool-runner` pod'u kaldirildi. Tool'lar artik Host Agent'lar uzerinde calisir. GitHub API, S3 gibi cloud tool'lar dogrudan ai-orchestrator icinden cagrilir.

### 5.2 Host Agent Makineleri

| Host ID | Makine | OS | Lokasyon | 7/24 | Ozel Yetenekler |
|---------|--------|----|----------|------|-----------------|
| macbook-pro | MacBook Pro | macOS 15+ | Lokal/Mobil | Hayir | Xcode, iOS Sim, Maestro iOS |
| macbook-air | MacBook Air | macOS 14 | Lokal/Mobil | Hayir | Android SDK, Maestro Android |
| ubuntu-dev | Ubuntu Server | Ubuntu 22.04 | Sabit (ofis/ev) | Evet | Node.js, Next.js, yuksek kaynak |

### 5.3 Network Yapisi

- **Ingress:** AWS ALB ile TLS termination, WebSocket upgrade destegi
- **iOS App → Backend:** WSS uzerinden, JWT auth
- **Host Agent → Backend:** WSS uzerinden, API key auth, agent protocol
- **Internal:** Pod'lar arasi iletisim Kubernetes service uzerinden
- **External:** Claude API, Deepgram, OpenAI TTS, GitHub API, S3 icin egress

### 5.4 Storage

- **PostgreSQL:** EBS volume (persistent)
- **Host Agent'lar:** Lokal gecici dosyalar (screenshot, log) → S3'e yuklenir
- **S3:** Dosya paylasimi, screenshot arsivi, audit log arsivi

### 5.5 Proje-Host Eslesmesi

```yaml
projects:
  - slug: project-x
    name: "Project X (iOS App)"
    primary_host: "macbook-pro"          # iOS projeleri sadece burada
    fallback_host: null                   # Fallback yok, Xcode gerekli
    path: "/Users/atakan/projects/project-x"

  - slug: project-y
    name: "Project Y (Android App)"
    primary_host: "macbook-air"           # Android projeleri burada
    fallback_host: null
    path: "/Users/atakan/dev/project-y"

  - slug: project-z
    name: "Project Z (Next.js Web)"
    primary_host: "ubuntu-dev"            # 7/24 acik, web projesi
    fallback_host: "macbook-pro"          # Ubuntu kapali ise Mac'te calistir
    path: "/home/atakan/projects/project-z"

  - slug: project-w
    name: "Project W (Node.js API)"
    primary_host: "ubuntu-dev"
    fallback_host: "macbook-air"
    path: "/home/atakan/projects/project-w"
```

**Routing Mantigi:**
1. AI bir tool calistirmak istediginde, projenin `primary_host`'una gonderir
2. Primary host cevimdisi ise `fallback_host`'a gonderir
3. Fallback da yoksa kullaniciya "Host X cevimdisi, islem yapilamiyor" bildirir
4. Cloud tool'lar (GitHub, S3, mem0) her zaman EKS uzerinde calisir, host gerekmez

---

## 6. Sirali Calisma Modeli

Sistem projeler uzerinde sirayla calisir (paralel degil). Bu tercih token tuketimini optimize eder.

### 6.1 Calisma Mantigi

- Her proje bagimsiz bir "task" olarak islenir
- Bir proje analizi tamamlanmadan digerine gecilmez
- Her proje sonucu aninda kullaniciya iletilir (topluca beklenmez)
- Kullanici isterse tek bir projeye odaklanabilir

### 6.2 Ileride Paralel Gecis

Performans yetersiz kalirsa, her proje icin ayri bir Claude API call yapilarak paralel moda gecilebilir. Backend mimarisi buna izin verecek sekilde tasarlanmistir (tool-runner pod'u scale edilebilir).

---

## 7. Deployment Fazlari

| Faz | Icerik | Tahmini Sure | Oncelik |
|-----|--------|--------------|---------|
| Faz 1 | Backend + Claude API + tool calling loop | 1 hafta | Kritik |
| Faz 1.5 | Host Agent (Mac + Ubuntu) + agent registry | 1 hafta | Kritik |
| Faz 2 | Docker tool + GitHub tool + Playwright tool | 1 hafta | Kritik |
| Faz 3 | mem0 memory entegrasyonu | 1 hafta | Yuksek |
| Faz 4 | iOS native app (SwiftUI + WebSocket + ses) | 2-3 hafta | Yuksek |
| Faz 5 | Maestro mobil test entegrasyonu | 3-5 gun | Orta |
| Faz 6 | Proaktif bildirimler + monitoring dashboard | 1 hafta | Orta |

**Toplam tahmini sure: 8-10 hafta**

Faz 1 + 1.5 tamamlandiginda backend ve host agent'lar iletisim kurabilir durumda olur. Faz 2-3 ile tool'lar ve memory eklenir. Faz 4 ile iOS uygulamasi devreye girer. Faz 5-6 iyilestirme fazlaridir.

---

*Bu dokuman RafRaf serisinin 1/8 numarali dokumanidir.*
*Sonraki dokuman: 02_Backend_API_WebSocket_Specification.md*
