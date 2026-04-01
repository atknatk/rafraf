# Dynamic Island Senaryolari

## Senaryo 1: Dynamic Island Shows Task Progress

**Onkosul:**
- iPhone 14 Pro veya uzeri (Dynamic Island destekli cihaz)
- Kullanici oturum acmis
- Bir proje secili durumda

**Adimlar:**
1. Kullanici bir AI task baslatir (ornegin "Login ekranini implement et")
2. Backend task'i kabul eder ve pipeline baslar
3. iOS app `LiveActivityManager.startTask()` cagirir
4. Dynamic Island compact view'da task basligi ve progress gosterilir

**Beklenen Davranis:**
- Compact leading: Phase icon (SF Symbol, ornegin `brain.head.profile` for architect)
- Compact trailing: Progress yuzde degeri (ornegin "45%")
- Expanded view: Task basligi, mevcut adim aciklamasi, progress bar, kalan sure
- Her pipeline faz degisiminde (planning → implementing → testing → reviewing) icon ve label guncellenir
- Progress 0.0'dan 1.0'a dogru artar, completedSteps/totalSteps orani gorsel olarak yansir

**Dogrulama:**
- `TaskActivityAttributes.ContentState` her update'te dogru degerler alir
- Dynamic Island compact leading/trailing icerik degisimleri gozlemlenir
- Expanded view'da tum alanlar (status, currentStep, progress, phaseIcon) goruntulenir

---

## Senaryo 2: Remote Push Updates Dynamic Island

**Onkosul:**
- iPhone 14 Pro veya uzeri
- Live Activity baslatilmis ve push token backend'e gonderilmis
- App arka planda veya tamamen kapali

**Adimlar:**
1. Kullanici bir task baslatir ve app'i arka plana atar (veya kapatir)
2. Backend pipeline ilerledikce APNs push notification gonderir
3. Push payload `TaskActivityAttributes.ContentState` formatinda JSON icerir:
   ```json
   {
     "aps": {
       "timestamp": 1711929600,
       "event": "update",
       "content-state": {
         "status": "testing",
         "currentStep": "Tester is running test suite...",
         "progress": 0.75,
         "completedSteps": 3,
         "totalSteps": 4,
         "estimatedSecondsRemaining": 60,
         "phaseIcon": "checkmark.circle"
       }
     }
   }
   ```
4. iOS sistemi push'u alir ve Dynamic Island / Lock Screen Live Activity'yi gunceller

**Beklenen Davranis:**
- App kapali olsa bile Dynamic Island guncellenir
- ContentState JSON payload'u basariyla decode edilir
- Guncellenen progress, status ve phaseIcon Dynamic Island'da yansir
- Lock Screen'de de Live Activity widget'i guncellenir
- Push token rotasyonu durumunda yeni token backend'e iletilir

**Dogrulama:**
- `TaskActivityAttributes.ContentState` APNs JSON'dan hatasiz decode edilir (unit test ile dogrulanir)
- Push token `activity.pushTokenUpdates` async sequence ile gozlemlenir
- App foreground'a donunce Live Activity state'i guncel olur

---

## Senaryo 3: Multiple Concurrent Tasks

**Onkosul:**
- iPhone 14 Pro veya uzeri
- Kullanici birden fazla projede ayni anda task calistiriyor

**Adimlar:**
1. Kullanici Proje A icin bir task baslatir → Live Activity #1 olusur
2. Kullanici Proje B icin ikinci bir task baslatir → Live Activity #2 olusur
3. Her iki task ayni anda ilerler

**Beklenen Davranis:**
- iOS, ayni anda birden fazla Live Activity destekler (sistem limiti 5)
- Dynamic Island **compact** view en son baslayan veya en yuksek oncelikli activity'yi gosterir
- Dynamic Island **minimal** view ikinci activity icin kucuk indicator gosterir (trailing minimal)
- Kullanici Dynamic Island'a uzun basarak tum aktif Live Activity'leri gorebilir
- Lock Screen'de her iki Live Activity ayri ayri listelenir
- Bir task tamamlandiginda ilgili Live Activity sonlanir, diger devam eder

**Dogrulama:**
- `LiveActivityManager` birden fazla activity'yi ayni anda yonetebilir
- Her activity bagimsiz `TaskActivityAttributes` ile olusturulur (farkli taskId)
- `endTask()` sadece ilgili activity'yi sonlandirir, digerleri etkilenmez
- Concurrent task senaryosunda race condition veya crash olmaz
