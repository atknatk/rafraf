# RafRaf — Security, Permissions & Cost Analysis

**Document 7/8** | Version 1.0 | March 2026

---

## 1. Genel Bakis

Bu dokuman sistemin guvenlik mimarisini, yetki kontrollerini, maliyet analizini ve monitoring stratejisini tanimlar. Sistem, shell komutu calistirma ve Docker yonetimi gibi hassas yeteneklere sahip oldugu icin guvenlik kritik oneme sahiptir.

---

## 2. Authentication (Kimlik Dogrulama)

### 2.1 JWT Token Sistemi

| Parametre | Deger |
|-----------|-------|
| Algoritma | HS256 |
| Access Token Suresi | 24 saat |
| Refresh Token Suresi | 30 gun |
| Token Depolama (iOS) | Keychain |
| Token Depolama (Backend) | Redis (blacklist) |

**Token Payload:**
```json
{
  "sub": "atakan",
  "iat": 1709312400,
  "exp": 1709398800,
  "device_id": "iphone-uuid",
  "permissions": ["read", "write", "tool_execute", "admin"]
}
```

### 2.2 Baglanti Akisi

```
1. iOS app → POST /auth/token (API key ile)
2. Backend → JWT access + refresh token dondurur
3. iOS app → WSS bağlantisi acar (token query param veya header)
4. Backend → Token dogrular, WebSocket acar
5. Token sure dolmadan → iOS app refresh token ile yeni access token alir
6. Refresh token suresi dolunca → Yeniden login gerekli
```

### 2.3 API Key Yonetimi

- Ilk kurulumda backend bir API key olusturur
- Bu key iOS app'e guvenli bir sekilde aktarilir (QR kod veya manual giris)
- API key ile JWT token alinir
- API key revoke edilebilir (cihaz kaybi durumunda)

---

## 3. Authorization (Yetkilendirme)

### 3.1 Iki Katmanli Yetki Sistemi

**Katman 1: Kullanici Yetkileri**
- Tek kullanici sistemi (su an icin multi-user yok)
- Tum yetkiler varsayilan olarak acik
- Ileride multi-user destegi icin role-based access control (RBAC) eklenebilir

**Katman 2: Tool Yetki Matrisi**

Bu matris, AI'in hangi islemleri onaysiz, hangilerini onay ile yapabilecegini tanimlar:

### 3.2 Detayli Yetki Matrisi

**Docker Islemleri:**

| Islem | Onay | Sebep |
|-------|------|-------|
| compose up (dev) | Onaysiz | Gelistirme ortami, risk dusuk |
| compose down (dev) | Onaysiz | Gelistirme ortami |
| compose restart | Onaysiz | Mevcut servisleri yeniden baslatma |
| compose logs | Onaysiz | Sadece okuma |
| compose ps | Onaysiz | Sadece okuma |
| container stats | Onaysiz | Sadece okuma |
| build | Onaysiz | Lokal build, kaynak tuketir ama zarar vermez |
| push | **ONAY** | Registry'ye image gonderme, geri alinamaz |
| compose up (prod) | **ONAY** | Production ortam |
| compose down (prod) | **ONAY** | Production ortam |
| prune | **ONAY** | Veri silme |

**GitHub Islemleri:**

| Islem | Onay | Sebep |
|-------|------|-------|
| list issues/PRs | Onaysiz | Sadece okuma |
| get issue/PR detail | Onaysiz | Sadece okuma |
| get diff/commits | Onaysiz | Sadece okuma |
| get actions status | Onaysiz | Sadece okuma |
| review PR (analiz) | Onaysiz | Sadece okuma, yorum yazmaz |
| create issue | **ONAY** | Yeni issue olusturma |
| close issue | **ONAY** | Issue durumu degisikligi |
| comment on issue/PR | **ONAY** | Herkese acik yorum |
| merge PR | **ONAY** | Kod degisikligi, geri alinmasi zor |

**Shell Islemleri:**

| Islem | Onay | Sebep |
|-------|------|-------|
| git status/log/diff | Onaysiz | Sadece okuma |
| ls/cat/head/tail/grep | Onaysiz | Sadece okuma |
| npm test/lint/build | Onaysiz | Lokal calistirma |
| python pytest/pylint | Onaysiz | Lokal calistirma |
| curl GET | Onaysiz | Sadece okuma |
| df/du/free/top/ps | Onaysiz | Sistem bilgisi okuma |
| kubectl * | **ONAY** | Kubernetes, tum komutlar |
| aws cli * | **ONAY** | AWS, tum komutlar |
| git push | **ONAY** | Remote degisikligi |
| npm publish | **ONAY** | Package yayinlama |
| rm (dosya silme) | **ONAY** | Veri kaybi riski |
| chmod/chown | **ONAY** | Yetki degisikligi |
| pip install (global) | **ONAY** | Sistem degisikligi |

**Tamamen Yasakli (Asla Calistirilmaz):**

| Komut | Sebep |
|-------|-------|
| rm -rf / | Sistem yok etme |
| mkfs * | Disk formatlama |
| dd if=/dev/zero | Disk silme |
| Fork bomb variants | Sistem kilitleme |
| shutdown/reboot/halt | Sistem kapatma |
| > /dev/sda | Disk uzerine yazma |

### 3.3 Onay Konfigurasyonu

```yaml
# approval_config.yaml

approval_rules:
  # Ortam bazli kurallar
  environments:
    production:
      all_writes: true         # Production'da tum yazma islemleri onay gerektirir
      docker_compose_up: true
      docker_compose_down: true
    development:
      all_writes: false
      docker_compose_up: false
      docker_compose_down: false

  # Tool bazli kurallar (ortamdan bagimsiz)
  always_require_approval:
    - "kubectl"
    - "aws"
    - "docker push"
    - "git push"
    - "npm publish"
    - "rm"
    - "chmod"
    - "chown"

  # Asla calistirilmayacaklar
  blacklisted_patterns:
    - "rm -rf /"
    - "rm -rf /*"
    - "mkfs"
    - "dd if=/dev"
    - ":()"
    - "shutdown"
    - "reboot"
    - "halt"
    - "> /dev/"

  # Onay timeout
  timeout_seconds: 300
  expired_action: "cancel"   # cancel | notify_only
```

---

## 4. Network Guvenligi

### 4.1 TLS/SSL

- Tum iletisim TLS 1.3 uzerinden
- WebSocket: WSS (WS degil)
- REST API: HTTPS
- Certificate: AWS Certificate Manager (ACM)

### 4.2 Network Isolation (EKS)

```yaml
# Kubernetes NetworkPolicy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: rafraf-network
spec:
  podSelector:
    matchLabels:
      app: rafraf
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: api-gateway
      ports:
        - port: 8000
  egress:
    # Claude API, Deepgram, OpenAI, GitHub, S3
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
      ports:
        - port: 443
```

### 4.3 Rate Limiting

| Endpoint | Limit | Periyot |
|----------|-------|---------|
| WebSocket mesaj | 30 | Dakika |
| Tool calistirma | 20 | Dakika |
| Auth token | 5 | Dakika |
| File upload | 10 | Dakika |
| Webhook | 100 | Dakika |

Redis tabanli sliding window rate limiter kullanilir.

### 4.4 IP Whitelist (Opsiyonel)

- iOS app'in kullandigi IP araliklari whitelist'lenebilir
- VPN kullanimi durumunda VPN cikis IP'si eklenir
- Varsayilan: Kapalı (tek kullanici, mobil agdan erisim)

---

## 5. Veri Guvenligi

### 5.1 Veri Siniflandirmasi

| Veri Tipi | Hassasiyet | Depolama | Sifreleme |
|-----------|------------|----------|-----------|
| JWT Token | Yuksek | Keychain (iOS), Redis (backend) | At-rest + in-transit |
| API Keys | Kritik | Kubernetes Secrets | At-rest |
| Konusma gecmisi | Orta | PostgreSQL | At-rest (EBS encryption) |
| Screenshots | Dusuk | S3 | Server-side (SSE-S3) |
| Audit log | Orta | PostgreSQL | At-rest |
| Ses kayitlari | Orta | Gecici (islem sonrasi silinir) | In-transit only |

### 5.2 S3 Guvenlik

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PreSignedURLOnly",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::rafraf-files/*",
      "Condition": {
        "StringNotEquals": {
          "s3:authType": "QueryString"
        }
      }
    }
  ]
}
```

- Tum dosya erisimi pre-signed URL ile
- URL suresi: 1 saat (screenshot), 24 saat (dokumanlar)
- Bucket public erisim: KAPALI
- Server-side encryption: Aktif

### 5.3 Secrets Yonetimi

- API key'ler Kubernetes Secrets'ta saklanir
- `.env` dosyalari Git'e commit edilmez
- Rotation: API key'ler 90 gunde bir yenilenir
- Ileride: AWS Secrets Manager veya HashiCorp Vault

---

## 6. Audit Trail (Denetim Izi)

### 6.1 Neleri Loglar?

Her tool calistirma su bilgilerle loglanir:

| Alan | Aciklama |
|------|----------|
| timestamp | Islem zamani |
| session_id | Hangi oturumda yapildi |
| tool_name | Hangi tool (docker, github, playwright vb.) |
| action | Hangi islem (compose_up, list_issues vb.) |
| project_id | Hangi proje uzerinde |
| input_params | Tool'a gonderilen parametreler |
| output_result | Tool sonucu (kisaltilmis) |
| success | Basarili mi? |
| error_message | Hata varsa detay |
| duration_ms | Islem suresi |
| approval_required | Onay gerektirdi mi? |
| approved_at | Ne zaman onaylandi? |
| model_used | Hangi Claude modeli kullanildi |
| tokens_used | Harcanan token |
| cost_usd | Islemin maliyeti |

### 6.2 Log Retention

| Log Tipi | Saklama Suresi |
|----------|---------------|
| Audit log | 1 yil |
| Conversation history | 90 gun |
| Screenshots | 30 gun |
| API call logs | 30 gun |
| Error logs | 90 gun |

### 6.3 Kullanici Erisimi

Kullanici "dun ne yaptin?" dediginde AI, audit log'dan son 24 saatin ozetini cikarabilir.

---

## 7. Maliyet Analizi

### 7.1 Claude API Maliyet Detayi

**Fiyatlandirma (Mart 2026):**

| Model | Input ($/M token) | Output ($/M token) |
|-------|-------------------|---------------------|
| Claude Sonnet 4.5 | $3.00 | $15.00 |
| Claude Haiku 4.5 | $0.25 | $1.25 |

**Gunluk Kullanim Senaryosu:**

| Islem | Model | Input Tokens | Output Tokens | Cagri Sayisi |
|-------|-------|-------------|--------------|--------------|
| Sabah proje kontrolu | Haiku | 20K | 5K | 4 |
| Durum sorgusu | Haiku | 8K | 2K | 6 |
| Docker start/stop | Haiku | 5K | 1K | 4 |
| Log okuma | Haiku | 15K | 3K | 3 |
| Kod review | Sonnet | 40K | 10K | 3 |
| Bug analizi | Sonnet | 30K | 8K | 2 |
| Test analizi | Sonnet | 25K | 6K | 2 |
| Genel sohbet | Haiku | 10K | 3K | 5 |

**Gunluk Toplam:**

| Model | Input | Output | Maliyet |
|-------|-------|--------|---------|
| Haiku | 200K | 50K | $0.11 |
| Sonnet | 285K | 72K | $1.94 |
| **Gunluk Toplam** | | | **$2.05** |

**Aylik Toplam (30 gun):** **~$61.50**

**Prompt Caching ile (~%30 tasarruf):** **~$43.00**

### 7.2 Diger API Maliyetleri

**Deepgram (Speech-to-Text):**

| Parametre | Deger |
|-----------|-------|
| Model | Nova-2 |
| Fiyat | $0.0043/dakika |
| Gunluk kullanim | ~15 dakika |
| Gunluk maliyet | $0.065 |
| **Aylik maliyet** | **~$2.00** |

**OpenAI TTS (Text-to-Speech):**

| Parametre | Deger |
|-----------|-------|
| Model | tts-1 |
| Fiyat | $15.00/1M karakter |
| Gunluk kullanim | ~5000 karakter |
| Gunluk maliyet | $0.075 |
| **Aylik maliyet** | **~$2.25** |

**OpenAI Embedding (mem0 icin):**

| Parametre | Deger |
|-----------|-------|
| Model | text-embedding-3-small |
| Fiyat | $0.02/1M token |
| Gunluk kullanim | ~50K token |
| Gunluk maliyet | $0.001 |
| **Aylik maliyet** | **~$0.03** |

### 7.3 AWS Altyapi Maliyetleri

| Kaynak | Konfigürasyon | Aylik Maliyet |
|--------|---------------|---------------|
| EKS ek pod'lar (5 pod) | t3.medium equivalent | ~$8-12 |
| RDS PostgreSQL | db.t3.micro | ~$15 (veya EKS icinde $0) |
| S3 | ~5GB/ay | ~$0.12 |
| ALB (Ingress) | 1 ALB | ~$16 |
| Data Transfer | ~10GB/ay | ~$1 |
| CloudWatch | Temel monitoring | ~$3 |
| **AWS Toplam** | | **~$30-45** |

Not: EKS cluster zaten mevcut, ek maliyet sadece yeni pod'lar ve S3 icin.

### 7.4 Toplam Aylik Maliyet Ozeti

| Kalem | Min | Max |
|-------|-----|-----|
| Claude API (Haiku+Sonnet, cached) | $43 | $65 |
| Deepgram STT | $2 | $5 |
| OpenAI TTS | $2 | $5 |
| OpenAI Embedding | $0.03 | $0.10 |
| AWS Ek Altyapi | $30 | $45 |
| **TOPLAM** | **$77** | **$120** |

### 7.5 Maliyet Optimizasyon Stratejileri

**Aninda uygulanabilir:**
- Prompt caching: ~%30 Claude API tasarrufu
- Model routing (Haiku vs Sonnet): ~%40 tasarruf vs tum Sonnet
- TTS sadece kisa cevaplar icin: ~%50 TTS tasarrufu

**Orta vadede:**
- Whisper local (faster-whisper): Deepgram maliyeti sifir olur
- Local embedding model: OpenAI embedding maliyeti sifir olur
- S3 lifecycle policy: 30 gun sonra Glacier'a tasima

**Uzun vadede:**
- Self-hosted LLM (Ollama): Basit isler icin, Claude API maliyetini azaltir
- Spot instances (EKS): ~%60 altyapi tasarrufu

### 7.6 Maliyet Alertleri

```yaml
# cost_alerts.yaml
alerts:
  daily:
    warning_threshold_usd: 8
    critical_threshold_usd: 15
    notification: push_notification
  monthly:
    warning_threshold_usd: 100
    critical_threshold_usd: 150
    notification: push_notification + email
  per_session:
    warning_threshold_usd: 2
    notification: in_app_warning
```

---

## 8. Monitoring ve Observability

### 8.1 Health Checks

| Servis | Endpoint | Kontrol Sikligi | Timeout |
|--------|----------|-----------------|---------|
| API Gateway | /health | 30 saniye | 5 saniye |
| AI Orchestrator | /health | 30 saniye | 5 saniye |
| Tool Runner | /health | 60 saniye | 10 saniye |
| mem0 Server | /health | 60 saniye | 5 saniye |
| PostgreSQL | pg_isready | 30 saniye | 3 saniye |
| Redis | PING | 30 saniye | 2 saniye |

### 8.2 Metrikler

**Sistem Metrikleri:**
- CPU/Memory kullanimi (her pod)
- Disk kullanimi
- Network I/O
- Pod restart sayisi

**Uygulama Metrikleri:**
- Aktif WebSocket baglanti sayisi
- Mesaj islenme suresi (p50, p95, p99)
- Claude API response suresi
- Tool calistirma suresi
- Hata orani (tool basina)
- Gunluk/aylik API maliyet

**Is Metrikleri:**
- Gunluk mesaj sayisi
- Tool kullanim dagilimi
- Onay talebi ortalama cevap suresi
- En sik kullanilan islemler
- Proje bazli kullanim

### 8.3 Alerting Kurallari

| Alert | Kosul | Kanal | Oncelik |
|-------|-------|-------|---------|
| API Gateway down | Health check 3x fail | Push + SMS | Kritik |
| Claude API hatasi | 5+ ardisik hata | Push | Yuksek |
| Yuksek maliyet | Gunluk > $15 | Push | Yuksek |
| Yavas response | p95 > 10 saniye | Log | Orta |
| Pod restart | > 3 restart/saat | Push | Yuksek |
| Disk dolu | > %85 | Push | Yuksek |
| WebSocket baglanti kopma | > 5/dakika | Log | Orta |

### 8.4 Dashboard

CloudWatch veya Grafana ile basit bir dashboard:

- Gunluk maliyet grafigi (servis bazli)
- Mesaj hacmi (saatlik)
- API response time (p50, p95)
- Tool kullanim pastasi
- Hata orani trendi
- Aktif session sayisi

---

## 9. Disaster Recovery

### 9.1 Yedekleme

| Veri | Yedekleme | Periyot | Saklama |
|------|-----------|---------|---------|
| PostgreSQL | pg_dump → S3 | Gunluk | 30 gun |
| mem0 vektörleri | pg_dump (ayni DB) | Gunluk | 30 gun |
| Konfigürasyon | Git repo | Her degisiklikte | Surekli |
| Screenshots | S3 (zaten) | - | 30 gun |

### 9.2 Recovery Zamanlari

| Senaryo | RTO (Recovery Time) | RPO (Data Loss) |
|---------|---------------------|-----------------|
| Pod crash | < 2 dakika (K8s restart) | 0 |
| DB crash | < 15 dakika (restore) | < 1 gun |
| Full cluster fail | < 1 saat | < 1 gun |

### 9.3 Failover Stratejisi

- API Gateway: 2 replica, birisi duserse digeri devam eder
- PostgreSQL: Single instance (maliyet sebebi), gunluk yedek
- Redis: Ephemeral, kayip kabul edilebilir (sadece cache)
- Ileride: Multi-AZ PostgreSQL, Redis cluster

---

## 10. Gelecek Gelistirmeler (Roadmap)

### 10.1 Kisa Vade (1-3 ay)

- Temel sistem kurulumu (Faz 1-4)
- Tum tool'larin implement edilmesi
- iOS app MVP
- mem0 entegrasyonu

### 10.2 Orta Vade (3-6 ay)

- Maestro mobil test entegrasyonu
- Proaktif bildirimler
- Visual regression testing
- Maliyet optimizasyonu (caching, model routing)
- Multi-project dashboard

### 10.3 Uzun Vade (6-12 ay)

- CI/CD entegrasyonu (GitHub Actions ile iki yonlu)
- Otomatik issue olusturma (test fail → issue)
- Performance trending (proje bazli metrikler zamanla)
- Multi-user destegi (takim kullanimi)
- Self-hosted LLM entegrasyonu (hibrit model)
- Android companion app
- Web dashboard

---

## 11. Dokuman Serisi Ozeti

| # | Dokuman | Icerik |
|---|---------|--------|
| 1 | System Architecture Overview | Genel mimari, tech stack, veri akisi, deployment fazlari |
| 2 | Backend API & WebSocket Specification | FastAPI, WebSocket protokolu, DB semasi, konfigürasyon |
| 3 | AI Agent & Tool Layer Specification | Claude Agent SDK, tool tanimlari, model router, onay mekanizmasi |
| 4 | iOS App Specification | SwiftUI, ekranlar, sesli iletisim, WebSocket yonetimi |
| 5 | Memory System Specification | mem0, 3 katmanli hafiza, fact extraction, context yonetimi |
| 6 | Testing Strategy | Playwright (web), Maestro (mobil), test senaryolari |
| 7 | Security, Permissions & Cost Analysis | Guvenlik, yetki matrisi, maliyet, monitoring, roadmap |
| 8 | Host Agent Specification | Mac + Ubuntu agent, multi-host yonetimi, kurulum |

---

*Bu dokuman RafRaf serisinin 7/8 numarali dokumanidir.*
*Onceki: 06_Testing_Strategy.md*
*Sonraki: 08_Host_Agent_Specification.md*
