# Feature: Interactive Question Cards (Approval + Countdown)

**Issue**: #30
**Faz**: F5
**Katmanlar**: ios
**Pipeline**: full
**Tarih**: 2026-03-03

## Ozet

Kullanici onay gerektiren islemler icin interaktif kart componentleri. Backend'den WebSocket uzerinden gelen `question` mesajlarina karsilik countdown timer ile onayla/reddet akisi sunar. Multi-choice question destegi ve animasyonlu gosterim/kapanma saglar. Timeout durumunda otomatik red gonderir.

## Degisecek Dosyalar

### iOS (`apps/ios/`)

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `RafRaf/Features/Approval/Data/DTOs/ApprovalQuestionDTO.swift` | CREATE | Approval question WS mesaj DTO |
| `RafRaf/Features/Approval/Data/DTOs/ApprovalResponseDTO.swift` | CREATE | Approval response WS mesaj DTO |
| `RafRaf/Features/Approval/Data/Mappers/ApprovalMapper.swift` | CREATE | DTO -> Domain model mapper |
| `RafRaf/Features/Approval/Data/Repositories/ApprovalRepositoryImpl.swift` | CREATE | WebSocket uzerinden approval response gonderme |
| `RafRaf/Features/Approval/Domain/Models/ApprovalQuestion.swift` | CREATE | Domain model: soru, secenekler, timeout, kategori |
| `RafRaf/Features/Approval/Domain/Models/ApprovalOption.swift` | CREATE | Domain model: buton secenegi (id, label, style) |
| `RafRaf/Features/Approval/Domain/Repositories/ApprovalRepositoryProtocol.swift` | CREATE | Repository protocol |
| `RafRaf/Features/Approval/Domain/UseCases/SubmitApprovalDecisionUseCase.swift` | CREATE | Onay/red kararini gonderme use case |
| `RafRaf/Features/Approval/Presentation/ViewModels/ApprovalCardViewModel.swift` | CREATE | ViewModel: countdown, karar, animasyon state |
| `RafRaf/Features/Approval/Presentation/Views/RFApprovalCard.swift` | CREATE | Ana approval card view (countdown + butonlar) |
| `RafRaf/Features/Approval/Presentation/Components/RFCountdownTimer.swift` | CREATE | Countdown timer gorsel component |
| `RafRaf/Features/Approval/Presentation/Components/RFApprovalOptionButton.swift` | CREATE | Tek secenek butonu (primary/danger/secondary stilli) |

## WebSocket Messages

Mevcut `shared/api-contracts/ws/approval-messages.json` kontrati kullanilir:

| Direction | Type | Payload | Aciklama |
|-----------|------|---------|----------|
| server->client | `question` | `QuestionPayload` | Kullaniciya onay sorusu gonder |
| client->server | `approval_response` | `ApprovalResponsePayload` | Kullanici karar cevabi |

## Data Model

### Swift Models

```swift
// Domain/Models/ApprovalQuestion.swift
struct ApprovalQuestion: Identifiable, Sendable, Equatable {
    let id: String           // approval_id (UUID)
    let question: String     // Soru metni
    let context: String?     // Ek bilgi
    let options: [ApprovalOption]  // Secenek listesi
    let timeoutSeconds: Int  // Bekleme suresi
    let category: ApprovalCategory // Onay kategorisi
    let receivedAt: Date     // Soru alinma zamani
}

// Domain/Models/ApprovalOption.swift
struct ApprovalOption: Identifiable, Sendable, Equatable {
    let id: String           // approve, reject, detail
    let label: String        // Gorunen etiket
    let style: ApprovalOptionStyle // primary, danger, secondary
}

enum ApprovalOptionStyle: String, Sendable, Equatable, CaseIterable {
    case primary
    case danger
    case secondary
}

enum ApprovalCategory: String, Sendable, Equatable, CaseIterable {
    case deploy
    case destructive
    case infrastructure
    case writeRemote = "write_remote"
}

enum ApprovalDecision: String, Sendable, Equatable {
    case approved
    case rejected
}
```

```swift
// Data/DTOs/ApprovalQuestionDTO.swift
struct ApprovalQuestionDTO: Codable, Sendable {
    let approvalId: String
    let question: String
    let context: String?
    let options: [ApprovalOptionDTO]
    let timeoutSeconds: Int
    let category: String
}

struct ApprovalOptionDTO: Codable, Sendable {
    let id: String
    let label: String
    let style: String
}

// Data/DTOs/ApprovalResponseDTO.swift
struct ApprovalResponseDTO: Codable, Sendable {
    let approvalId: String
    let decision: String
    let note: String?
}
```

## Business Rules

1. Approval kart gosterimi: Backend `question` mesaji geldiginde chat akisinda approval card render edilir
2. Countdown timer: `timeout_seconds` degerinden geri sayim baslar (varsayilan 30sn)
3. Timeout: Geri sayim sifira ulastiginda otomatik `rejected` karari gonderilir
4. Tek aktif approval: Bir seferde sadece bir approval card aktif olabilir
5. Karar sonrasi: Kart animasyonlu kapanir, sonuc chat akisinda gosterilir
6. Kategori renkleri: `destructive` ve `deploy` kategorileri kirmizi vurgu, diger kategoriler standart
7. Spring animation: Kart gosterim ve kapanma animasyonlari spring tipinde
8. Approval matrisi: `docs/07_Security_Permissions_Cost_Analysis.md` Bolum 3.2'ye uygun
9. Buton stilleri: API'daki `style` field'i dogrudan RFButton stillerine map edilir (primary->primary, danger->destructive, secondary->secondary)

## Test Requirements

### iOS
- [ ] Unit test: ApprovalCardViewModel - countdown logic
- [ ] Unit test: ApprovalCardViewModel - timeout auto-rejection
- [ ] Unit test: ApprovalCardViewModel - karar gonderme (approve/reject)
- [ ] Unit test: ApprovalMapper - DTO->Domain mapping
- [ ] Unit test: ApprovalQuestionDTO decoding from JSON
- [ ] Unit test: ApprovalResponseDTO encoding to JSON
- [ ] Unit test: SubmitApprovalDecisionUseCase - basari ve hata senaryolari

## Acceptance Criteria

- [ ] RFApprovalCard componenti olusturuldu
- [ ] Countdown timer (varsayilan 30sn) calisir
- [ ] Onayla / Reddet butonlari calisir
- [ ] Multi-choice question destegi (birden fazla secenek)
- [ ] Animasyonlu gosterim/kapanma (spring animation)
- [ ] Timeout durumunda otomatik red
- [ ] Onay/red sonucu backend'e gonderilir (WebSocket approval_response)
- [ ] #Preview mevcut
- [ ] Unit testler yazildi
- [ ] Coverage >= 70%
