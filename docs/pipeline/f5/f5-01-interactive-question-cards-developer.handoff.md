# Developer Handoff: Interactive Question Cards (Approval + Countdown)

**Issue**: #30
**Branch**: feature/f5/30-f5-01-interactive-question-cards
**Tarih**: 2026-03-03
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `RafRaf/Features/Approval/Domain/Models/ApprovalQuestion.swift` | CREATE | ApprovalQuestion, ApprovalCategory, ApprovalDecision domain modelleri |
| `RafRaf/Features/Approval/Domain/Models/ApprovalOption.swift` | CREATE | ApprovalOption, ApprovalOptionStyle domain modelleri |
| `RafRaf/Features/Approval/Domain/Repositories/ApprovalRepositoryProtocol.swift` | CREATE | Repository protokolu - submitDecision |
| `RafRaf/Features/Approval/Domain/UseCases/SubmitApprovalDecisionUseCase.swift` | CREATE | Onay karari gonderme use case |
| `RafRaf/Features/Approval/Data/DTOs/ApprovalQuestionDTO.swift` | CREATE | WebSocket question mesaj DTO + ApprovalOptionDTO |
| `RafRaf/Features/Approval/Data/DTOs/ApprovalResponseDTO.swift` | CREATE | WebSocket approval_response mesaj DTO |
| `RafRaf/Features/Approval/Data/Mappers/ApprovalMapper.swift` | CREATE | DTO <-> Domain mapper fonksiyonlari |
| `RafRaf/Features/Approval/Data/Repositories/ApprovalRepositoryImpl.swift` | CREATE | WebSocket uzerinden approval response gonderme |
| `RafRaf/Features/Approval/Presentation/ViewModels/ApprovalCardViewModel.swift` | CREATE | ViewModel: countdown timer, karar, timeout, animasyon state |
| `RafRaf/Features/Approval/Presentation/Views/RFApprovalCard.swift` | CREATE | Ana approval card view (countdown + kategori badge + butonlar) |
| `RafRaf/Features/Approval/Presentation/Components/RFCountdownTimer.swift` | CREATE | Dairesel countdown timer gorsel componenti |
| `RafRaf/Features/Approval/Presentation/Components/RFApprovalOptionButton.swift` | CREATE | Secenek butonu (style mapping: primary/danger/secondary) |
| `RafRaf/Core/DI/AppContainer.swift` | MODIFY | Approval feature DI kayitlari eklendi |

## API Kontrat Uyumu

- Referans: `shared/api-contracts/ws/approval-messages.json`
- Dogrulanan mesaj tipleri: 2 (question server->client, approval_response client->server)
- DTO field isimleri kontrat ile birebir uyumlu (approval_id, question, context, options, timeout_seconds, category, decision, note)
- Yapilan duzeltmeler: Yok - kontrat ile tam uyumlu

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| swiftlint | N/A | CI'da calistirilacak |
| xcodebuild build | N/A | CI'da calistirilacak (iOS only target) |
| xcodebuild test | N/A | CI'da calistirilacak |

## Notlar

- Clean Architecture katman izolasyonu korundu (Domain'den Data/Presentation import yok)
- Tum RF* bilesenler kullanildi: RFButton, RFText, RFCard, RFColors, RFSpacing
- Yeni RF* bilesenler: RFApprovalCard, RFCountdownTimer, RFApprovalOptionButton
- Tum stringler `String(localized:)` ile localized
- Her view'da `#Preview` blogu var (3 preview variant: standard, multi-choice, destructive)
- ViewModel: `@Observable` + `@MainActor` pattern
- Countdown: Task-based timer, her saniye guncelleme
- Timeout: Otomatik rejection gonderme (rejected + "Timeout - otomatik red" notu)
- Spring animation: Kart gosterim/kapanma icin .spring(response:dampingFraction:)
- Kategori bazli stil: destructive/deploy -> kirmizi border ve badge
- Force unwrap kullanilmadi (guard let, nil coalescing pattern)
- Any tipi kullanilmadi
- Tum fonksiyon parametreleri ve donus tipleri typed
