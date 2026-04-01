# Task Tracking Acceptance Scenarios

## Scenario 1: App Launch with Active Tasks

**Given** kullanici daha once bir AI task baslatmis ve uygulama kapatilmis
**And** backend'de task hala "implementing" durumunda (%45 ilerleme)
**When** kullanici uygulamayi yeniden acar
**Then** uygulama WebSocket baglantisi kurar
**And** GET /api/v1/tasks/active endpoint'ini cagirarak aktif task'lari alir
**Then** TaskListView'da aktif task gorunur:
  - Task basligi goruntulenir
  - Proje adi goruntulenir
  - Mevcut adim ("developer") goruntulenir
  - Ilerleme cubugu %45 gosterir
  - Tamamlanan adim sayisi (1/4) gosterilir
**And** Dynamic Island'da (eger destekleniyorsa) Live Activity yeniden baslatilir
**And** Live Activity push token backend'e kaydedilir (PATCH /api/v1/tasks/{id}/live-activity)

### Edge Cases:
- Birden fazla aktif task varsa hepsi listelenmeli
- Backend erisilemezse hata mesaji gosterilmeli
- Token expired ise token yenilendikten sonra tekrar denenmeli

---

## Scenario 2: Real-time Task Update via WebSocket

**Given** kullanici uygulamada ve bir aktif task mevcut (%25, "planning" asamasinda)
**When** backend task_status WebSocket mesaji gonderir:
```json
{
    "type": "task_status",
    "content": {
        "task_id": "uuid-123",
        "status": "implementing",
        "current_step": "developer",
        "progress_pct": 45,
        "completed_steps": 1,
        "total_steps": 4,
        "detail": "Creating LoginView.swift..."
    }
}
```
**Then** TaskListView'daki ilgili task anlik guncellenir:
  - Status "implementing" olarak degisir
  - Ilerleme cubugu %25'ten %45'e animasyonlu gecer
  - Mevcut adim "developer" olarak guncellenir
  - Tamamlanan adim sayisi 1/4 gosterir
**And** Live Activity (Dynamic Island) ayni anda guncellenir
**And** Lock Screen widget progress bar guncellenir

### Terminal Status:
**When** backend task_status mesaji "completed" status ile gelir:
```json
{
    "type": "task_status",
    "content": {
        "task_id": "uuid-123",
        "status": "completed",
        "progress_pct": 100,
        "completed_steps": 4,
        "total_steps": 4,
        "result_summary": "Feature implemented successfully. 3 files created."
    }
}
```
**Then** TaskListView'da task "tamamlandi" olarak isaretlenir
**And** Live Activity "end" event'i ile sonlandirilir
**And** Basari bildirimi gosterilir (in-app banner)

### Failed Status:
**When** backend task_status mesaji "failed" status ile gelir
**Then** TaskListView'da task hata durumunda gosterilir
**And** Hata mesaji goruntulenir
**And** "Tekrar Dene" butonu gosterilir

---

## Scenario 3: App Reopened After Background

**Given** kullanici bir task baslatmis ve uygulama arka plana alinmis (home butonuna basmis)
**And** arka planda iken backend task'i %60'tan %85'e ilerletmis
**And** APNs uzerinden Live Activity push gonderilmis (Dynamic Island guncellenmis)
**When** kullanici uygulamayi tekrar on plana getirir
**Then** WebSocket yeniden baglanir (eger kopmussa)
**And** GET /api/v1/tasks/active cagrilarak en son durum senkronize edilir
**And** TaskListView listedeki task %85 ilerleme ile guncellenir
**And** Live Activity mevcut durumla uyumlu devam eder
**And** Aradaki kacirilmis WebSocket mesajlari icin state tam olarak kurtarilir

### WebSocket Reconnect:
**Given** uygulama arka planda iken WebSocket baglantisi kopmustu
**When** uygulama on plana donunce
**Then** WebSocketClient otomatik olarak yeniden baglanir
**And** Baglanti kurulduktan sonra hemen GET /api/v1/tasks/active cagirilir
**And** Mevcut in-memory task state ile server state karsilastirilir
**And** Farkliliklar varsa UI guncellenir (progress, status degisiklikleri)

### App Killed (Cold Start):
**Given** kullanici bir task baslatmis ve uygulamayi tamamen kapatmis (kill)
**And** arka planda backend task'i tamamlamis (completed)
**And** APNs push notification gonderilmis (visible, sound)
**When** kullanici push notification'a tiklar
**Then** Uygulama acilir
**And** Deep link ile TaskDetailView'a yonlendirilir
**And** Task detaylari goruntulenir (tamamlanmis durum, sonuc ozeti)

### Multiple Tasks:
**Given** kullanici ayni anda 2 farkli task baslatmis
**When** uygulama yeniden acildiginda
**Then** her iki task da GET /api/v1/tasks/active ile alinir
**And** TaskListView'da her iki task da listelenir
**And** Her task icin bagimsiz Live Activity gosterilir (iOS max 5 concurrent Live Activity destekler)
