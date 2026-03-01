# AI Project Supervisor — iOS App Specification

**Document 4/8** | Version 1.0 | March 2026

---

## 1. Genel Bakis

Native iOS uygulamasi, kullanici ile AI Supervisor arasindaki birincil arayuzdur. SwiftUI ile gelistirilir. Sesli ve metin tabanli iletisim, interaktif soru-cevap, gorsel icerik goruntuleme ve dosya paylasimi saglar.

### 1.1 Hedef Platform

| Ozellik | Deger |
|---------|-------|
| Minimum iOS | 17.0 |
| Framework | SwiftUI |
| Dil | Swift 5.9+ |
| Mimari | MVVM + Combine/async-await |
| Network | URLSession WebSocket + REST |
| Ses | AVFoundation + Deepgram SDK |
| Bildirim | APNs (Push Notification) |
| Depolama | SwiftData (lokal cache) |

---

## 2. Uygulama Mimarisi

### 2.1 Katmanli Yapi

```
┌──────────────────────────────────┐
│         UI Layer (SwiftUI)       │
│  Views, Components, Modifiers    │
├──────────────────────────────────┤
│       ViewModel Layer            │
│  ChatViewModel, ProjectsVM      │
│  SettingsVM, VoiceVM             │
├──────────────────────────────────┤
│       Service Layer              │
│  WebSocketService                │
│  VoiceService (STT/TTS)         │
│  S3FileService                   │
│  NotificationService             │
│  AuthService                     │
├──────────────────────────────────┤
│       Data Layer                 │
│  SwiftData (local cache)         │
│  KeychainManager (auth tokens)   │
│  UserDefaults (preferences)      │
└──────────────────────────────────┘
```

### 2.2 Proje Dizin Yapisi

```
AISupervisor/
├── App/
│   ├── AISupervisorApp.swift          # App entry point
│   ├── AppDelegate.swift              # Push notification handling
│   └── ContentView.swift              # Root navigation
│
├── Core/
│   ├── Network/
│   │   ├── WebSocketManager.swift     # WebSocket baglanti yonetimi
│   │   ├── APIClient.swift            # REST API client
│   │   └── MessageProtocol.swift      # Mesaj encode/decode
│   │
│   ├── Voice/
│   │   ├── SpeechRecognizer.swift     # Deepgram STT entegrasyonu
│   │   ├── SpeechSynthesizer.swift    # OpenAI TTS playback
│   │   └── AudioSessionManager.swift  # Ses oturumu yonetimi
│   │
│   ├── Auth/
│   │   ├── AuthManager.swift          # JWT token yonetimi
│   │   └── KeychainHelper.swift       # Guvenli token depolama
│   │
│   ├── Storage/
│   │   ├── S3FileManager.swift        # S3 upload/download
│   │   └── LocalCacheManager.swift    # Offline cache
│   │
│   └── Notifications/
│       └── PushNotificationManager.swift
│
├── Features/
│   ├── Chat/
│   │   ├── ChatView.swift             # Ana chat ekrani
│   │   ├── ChatViewModel.swift        # Chat is mantigi
│   │   ├── MessageBubble.swift        # Mesaj baloncugu
│   │   ├── VoiceInputButton.swift     # Sesli input butonu
│   │   ├── QuestionCard.swift         # Interaktif soru karti
│   │   ├── ScreenshotViewer.swift     # Screenshot goruntuleme
│   │   ├── StatusCard.swift           # Proje durum karti
│   │   ├── ProgressIndicator.swift    # Ilerleme gostergesi
│   │   ├── ActionResultView.swift     # Komut sonucu gorunumu
│   │   └── ErrorBanner.swift          # Hata bildirimi
│   │
│   ├── Projects/
│   │   ├── ProjectListView.swift      # Proje listesi
│   │   ├── ProjectDetailView.swift    # Proje detay sayfasi
│   │   └── ProjectViewModel.swift
│   │
│   ├── Settings/
│   │   ├── SettingsView.swift         # Ayarlar ekrani
│   │   ├── VoiceSettingsView.swift    # Ses ayarlari
│   │   └── NotificationSettingsView.swift
│   │
│   └── Onboarding/
│       ├── OnboardingView.swift       # Ilk kullanim rehberi
│       └── APIKeySetupView.swift      # API key girisi
│
├── Models/
│   ├── Message.swift                  # Mesaj veri modeli
│   ├── Project.swift                  # Proje veri modeli
│   ├── Question.swift                 # Interaktif soru modeli
│   ├── Attachment.swift               # Ek dosya modeli
│   └── ServerStatus.swift             # Sunucu durum modeli
│
├── Utilities/
│   ├── Constants.swift
│   ├── Extensions/
│   │   ├── Date+Extensions.swift
│   │   ├── Color+Theme.swift
│   │   └── String+Extensions.swift
│   └── Helpers/
│       ├── HapticFeedback.swift
│       └── MarkdownRenderer.swift
│
└── Resources/
    ├── Assets.xcassets
    ├── Localizable.strings (tr, en)
    └── Info.plist
```

---

## 3. Ekranlar ve UI Tasarimi

### 3.1 Ana Chat Ekrani (ChatView)

Bu uygulamanin ana ekranidir. Tum iletisim buradan yapilir.

```
┌────────────────────────────────────────┐
│ ◀  AI Supervisor          ⚙️  📊      │  ← Navigation bar
├────────────────────────────────────────┤
│                                        │
│  ┌──────────────────────────┐          │
│  │ 🤖 Gunaydin! 3 projede   │          │  ← AI mesaji
│  │ guncelleme var. Detay     │          │
│  │ ister misiniz?            │          │
│  └──────────────────────────┘          │
│                                        │
│          ┌──────────────────────────┐  │
│          │ Proje X'in durumunu      │  │  ← Kullanici mesaji
│          │ kontrol et               │  │
│          └──────────────────────────┘  │
│                                        │
│  ┌──────────────────────────┐          │
│  │ 🤖 Proje X kontrol        │          │
│  │ ediliyor...               │          │
│  │ ██████░░░░ %60            │          │  ← Progress indicator
│  └──────────────────────────┘          │
│                                        │
│  ┌──────────────────────────┐          │
│  │ 📊 Proje X Durumu         │          │
│  │ ┌────────────────────────┐│          │  ← Status card
│  │ │ Issues: 5 acik, 2 WIP  ││          │
│  │ │ Docker: ✅ Calisiyor    ││          │
│  │ │ Tests:  43/45 passed   ││          │
│  │ │ Son commit: 2 saat once││          │
│  │ └────────────────────────┘│          │
│  └──────────────────────────┘          │
│                                        │
│  ┌──────────────────────────┐          │
│  │ 📸 Screenshot              │          │
│  │ ┌────────────────────────┐│          │  ← Screenshot inline
│  │ │   [site screenshot]     ││          │
│  │ └────────────────────────┘│          │
│  └──────────────────────────┘          │
│                                        │
├────────────────────────────────────────┤
│  📎  │ Mesajinizi yazin...    │ 🎤  📤 │  ← Input bar
└────────────────────────────────────────┘
```

### 3.2 Interaktif Soru Karti (QuestionCard)

Onay gerektiren islemlerde gosterilir:

```
┌────────────────────────────────────────┐
│  ⚠️  Onay Gerekiyor                    │
│                                        │
│  Proje X'i production ortamina         │
│  deploy etmek istiyor musunuz?         │
│                                        │
│  Son testler basarili.                 │
│  3 yeni feature, 2 bug fix mevcut.    │
│                                        │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │ ✅ Onayla │ │ ❌ Reddet │ │ Detay  │ │
│  └──────────┘ └──────────┘ └────────┘ │
│                                        │
│  ⏱ 4:32 kaldi                          │
└────────────────────────────────────────┘
```

### 3.3 Proje Listesi (ProjectListView)

```
┌────────────────────────────────────────┐
│ ◀  Projeler                            │
├────────────────────────────────────────┤
│                                        │
│  ┌────────────────────────────────────┐│
│  │ 🟢 Project X            PRODUCTION ││
│  │ Next.js + Node.js + PostgreSQL     ││
│  │ 5 acik issue | Docker: ✅          ││
│  └────────────────────────────────────┘│
│                                        │
│  ┌────────────────────────────────────┐│
│  │ 🟡 Project Y            DEVELOPMENT││
│  │ Python + FastAPI + MongoDB         ││
│  │ 8 acik issue | Docker: ⚠️          ││
│  └────────────────────────────────────┘│
│                                        │
│  ┌────────────────────────────────────┐│
│  │ 🟢 Project Z            DEVELOPMENT││
│  │ React Native + Node.js            ││
│  │ 3 acik issue | Build: ✅           ││
│  └────────────────────────────────────┘│
│                                        │
└────────────────────────────────────────┘
```

### 3.4 Ayarlar (SettingsView)

```
┌────────────────────────────────────────┐
│ ◀  Ayarlar                             │
├────────────────────────────────────────┤
│                                        │
│  BAGLANTI                              │
│  ┌────────────────────────────────────┐│
│  │ Sunucu URL    api.supervisor.com   ││
│  │ Durum         🟢 Bagli             ││
│  │ Ping          45ms                 ││
│  └────────────────────────────────────┘│
│                                        │
│  SES AYARLARI                          │
│  ┌────────────────────────────────────┐│
│  │ Sesli Cevap        [ON/OFF]       ││
│  │ Ses Dili            Turkce         ││
│  │ Ses Hizi            1.0x           ││
│  │ Otomatik Dinleme    [ON/OFF]       ││
│  └────────────────────────────────────┘│
│                                        │
│  BILDIRIMLER                           │
│  ┌────────────────────────────────────┐│
│  │ Push Bildirimler    [ON/OFF]       ││
│  │ Onay Istekleri      [ON/OFF]       ││
│  │ CI/CD Hatalar       [ON/OFF]       ││
│  │ Gunluk Ozet         [ON/OFF]       ││
│  └────────────────────────────────────┘│
│                                        │
│  MALIYET                               │
│  ┌────────────────────────────────────┐│
│  │ Bu Ay              $67.30          ││
│  │ Bugun              $3.20           ││
│  │ Gunluk Limit       $10.00          ││
│  └────────────────────────────────────┘│
│                                        │
└────────────────────────────────────────┘
```

---

## 4. Sesli Iletisim

### 4.1 Speech-to-Text (Deepgram)

**Akis:**
1. Kullanici mikrofon butonuna basar (veya basili tutar)
2. Ses kaydi baslar (AVAudioEngine)
3. Ses verisi Deepgram WebSocket'ine streaming olarak gonderilir
4. Deepgram anlik transkripsiyon dondurur
5. Interim sonuclar ekranda gosterilir (kullanici ne soyledigini gorur)
6. Final transkripsiyon backend'e gonderilir

**Deepgram Konfigurasyonu:**
```json
{
  "model": "nova-2",
  "language": "tr",
  "smart_format": true,
  "punctuate": true,
  "interim_results": true,
  "endpointing": 500,
  "vad_events": true
}
```

**Iki Mod:**
- **Push-to-talk:** Butona basili tutarken konusma. Birakinca gonderme. (Default)
- **Hands-free:** Otomatik ses algilama (VAD). Susunca gonderme. (Ayarlardan aciilir)

### 4.2 Text-to-Speech (OpenAI TTS)

**Akis:**
1. AI metin cevabi gelir
2. Cevap OpenAI TTS API'a gonderilir
3. Ses dosyasi (mp3/opus) dondurulur
4. iOS app sesi oynatir (AVAudioPlayer)

**Konfigürasyon:**
```json
{
  "model": "tts-1",
  "voice": "nova",
  "response_format": "opus",
  "speed": 1.0
}
```

**Akilli Ses Kararlari:**
- Kisa cevaplar (< 100 karakter): Her zaman sesli
- Orta cevaplar (100-500 karakter): Sesli + metin
- Uzun cevaplar (> 500 karakter): Sadece metin (TTS maliyet optimizasyonu)
- Kod bloklari: Asla sesli okumaz
- Screenshot/gorsel: "Screenshot'i gonderiyorum" deyip gorsel gonderir

### 4.3 Ses Oturumu Yonetimi

- Diger uygulamalarin sesini kismaz (mix mode)
- Kulaklik takili ise otomatik hands-free mod
- Bluetooth kulaklik destegi
- Arkaplan ses kaydi YOK (gizlilik)

---

## 5. WebSocket Yonetimi

### 5.1 Baglanti Yasam Dongusu

```
App Acildi → JWT Token Al → WebSocket Baglan → connection_ack
    │
    ├── Baglanti Aktif → Heartbeat (30sn) → Mesaj Alisverisi
    │
    ├── Baglanti Koptu → Exponential Backoff Retry
    │   (1s → 2s → 4s → 8s → 16s → max 30s)
    │
    ├── App Arkaplan → WebSocket Kapat → Push Notification'a Gec
    │
    └── App Onplan → WebSocket Yeniden Baglan → Kacirilmis Mesajlari Al
```

### 5.2 Offline / Arkaplan Davranisi

- App arkaplanda iken WebSocket kapatilir (pil tasarrufu)
- Kritik bildirimler Push Notification ile gelir
- App tekrar acildiginda WebSocket baglanir
- Kacirilmis mesajlar REST API uzerinden cekilir (`GET /api/messages/missed?since={timestamp}`)

### 5.3 Reconnect Stratejisi

```swift
// Exponential backoff ile reconnect
private var reconnectDelay: TimeInterval = 1.0
private let maxReconnectDelay: TimeInterval = 30.0

func reconnect() {
    DispatchQueue.main.asyncAfter(deadline: .now() + reconnectDelay) {
        self.connect()
        self.reconnectDelay = min(self.reconnectDelay * 2, self.maxReconnectDelay)
    }
}

func onConnected() {
    self.reconnectDelay = 1.0  // Reset on successful connection
}
```

---

## 6. Mesaj Goruntuleme Bileşenleri

### 6.1 Mesaj Tipi → UI Bilesen Eslesmesi

| Mesaj Tipi | UI Bilesen | Ozellikler |
|------------|------------|------------|
| text | MessageBubble | Markdown render, kod vurgulama |
| voice | MessageBubble + AudioPlayer | Play/pause butonu, dalga formu |
| screenshot | ScreenshotViewer | Tam ekran zoom, pinch-to-zoom |
| question | QuestionCard | Butonlar, geri sayim, haptic feedback |
| status | StatusCard | Renkli gostergeler, kucuk grafikler |
| progress | ProgressIndicator | Animasyonlu ilerleme cubugu |
| action_result | ActionResultView | Basari/hata ikonu, genisletilebilir detay |
| error | ErrorBanner | Kirmizi banner, retry butonu |

### 6.2 Markdown Rendering

AI'in metin cevaplari Markdown icerebilir. iOS'ta render edilecek ogeler:

- **Bold** ve *italic* metin
- `inline kod` ve kod bloklari (syntax highlighting ile)
- Basliklar (H1-H3)
- Listeler (sirali ve sirasiz)
- Linkler (tiklanaabilir)
- Tablolar (basit)

**Kutuphane Onerisi:** `swift-markdown` (Apple resmi) + custom renderer

---

## 7. Dosya Paylasimi (S3 Entegrasyonu)

### 7.1 Kullanici → AI Dosya Gonderme

```
1. Kullanici 📎 butonuna tiklar
2. iOS dosya picker acilir (Photos, Files, Camera)
3. Secilen dosya S3'e yuklenir (pre-signed upload URL ile)
4. S3 URL'si WebSocket uzerinden backend'e gonderilir
5. AI dosyayi indirir ve analiz eder
```

### 7.2 AI → Kullanici Dosya Gonderme

```
1. AI screenshot veya dosya uretir
2. Dosya S3'e yuklenir
3. Pre-signed download URL iOS app'e gonderilir
4. iOS app dosyayi indirir ve gosterir
5. Kullanici isterse cihaza kaydedebilir
```

### 7.3 Desteklenen Dosya Turleri

| Tur | Uzanti | Max Boyut | Kullanim |
|-----|--------|-----------|----------|
| Gorsel | png, jpg, gif | 10MB | Screenshot, mockup, tasarim |
| Dokuman | pdf, docx, md | 20MB | Spesifikasyon, rapor |
| Kod | py, js, ts, swift | 5MB | Kod parcasi review |
| Log | txt, log | 10MB | Hata loglari |
| Arsiv | zip | 50MB | Proje dosyalari |

---

## 8. Push Notifications

### 8.1 Bildirim Turleri

| Tur | Oncelik | Ses | Ornek |
|-----|---------|-----|-------|
| Onay Istegi | critical | Evet | "Proje X deploy icin onay bekliyor" |
| CI/CD Hatasi | high | Evet | "Proje Y: GitHub Actions build fail" |
| Test Hatasi | high | Hayir | "Proje X: 2 test fail oldu" |
| Gunluk Ozet | normal | Hayir | "Gunluk rapor hazir: 3 proje kontrol edildi" |
| Bilgi | low | Hayir | "Proje Z: Docker servisleri baslatildi" |

### 8.2 Bildirim Akisi

```
Backend → APNs (Apple Push Notification Service) → iOS App
```

- Critical bildirimler: Do Not Disturb modunda bile gosterilir
- Kullanici her bildirim turunu ayarlardan acip kapatabilir
- Bildirime tiklaninca ilgili konusmaya yonlendirilir

---

## 9. Tema ve Tasarim

### 9.1 Renk Paleti

| Kullanim | Light Mode | Dark Mode |
|----------|------------|-----------|
| Background | #FFFFFF | #1C1C1E |
| Surface | #F2F2F7 | #2C2C2E |
| Primary | #1B2A4A | #5B9BD5 |
| Success | #34C759 | #30D158 |
| Warning | #FF9500 | #FFD60A |
| Error | #FF3B30 | #FF453A |
| AI Bubble | #E8F0FE | #1E3A5F |
| User Bubble | #1B2A4A | #5B9BD5 |
| Text Primary | #000000 | #FFFFFF |
| Text Secondary | #8E8E93 | #98989D |

### 9.2 Tipografi

| Kullanim | Font | Size |
|----------|------|------|
| Navigation Title | SF Pro Display Bold | 17pt |
| Message Text | SF Pro Text Regular | 16pt |
| Code | SF Mono | 14pt |
| Caption | SF Pro Text Regular | 13pt |
| Status Badge | SF Pro Text Medium | 12pt |

### 9.3 Animasyonlar

- Mesaj gelisinde: Altan kayarak gelme (slide up + fade in)
- Progress: Yumusak ilerleme animasyonu
- Soru karti: Scale + bounce efekti ile dikkat cekme
- Ses kaydi: Dalga formu animasyonu (pulsating)
- Baglanti durumu: Renk gecisi animasyonu

---

## 10. Guvenlik

### 10.1 Token Yonetimi

- JWT token Keychain'de saklanir (UserDefaults'ta DEGIL)
- Token suresi: 24 saat
- Refresh token: 30 gun
- App her acilisinda token gecerliligi kontrol edilir
- Biometric authentication (Face ID / Touch ID) opsiyonel

### 10.2 Veri Guvenligi

- Tum iletisim TLS 1.3 uzerinden (WSS/HTTPS)
- Lokal cache sifrelenmis (Data Protection: Complete)
- Screenshot cache: 24 saat sonra otomatik silinir
- Ses kayitlari: Islem sonrasi hemen silinir (cihazda saklanmaz)

---

## 11. Performans Gereksinimleri

| Metrik | Hedef |
|--------|-------|
| App acilis suresi | < 2 saniye |
| WebSocket baglanti | < 1 saniye |
| Mesaj gonderme latency | < 100ms |
| Ses kaydi baslatma | < 200ms |
| Screenshot goruntuleme | < 500ms (indirme dahil) |
| Memory kullanimi | < 150MB (normal kullanim) |
| Pil tuketimi | < %5/saat (aktif kullanim) |

---

*Bu dokuman AI Project Supervisor serisinin 4/8 numarali dokumanidir.*
*Onceki: 03_AI_Agent_Tool_Layer_Specification.md*
*Sonraki: 05_Memory_System_Specification.md*
