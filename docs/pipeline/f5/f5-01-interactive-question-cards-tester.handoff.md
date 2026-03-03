# Tester Handoff: Interactive Question Cards (Approval + Countdown)

**Issue**: #30
**Branch**: feature/f5/30-f5-01-interactive-question-cards
**Tarih**: 2026-03-03
**Sonraki Agent**: reviewer

## Coverage Raporu

| Platform | Coverage % | Esik | Durum |
|----------|-----------|------|-------|
| iOS (RafRaf/) | N/A (CI'da hesaplanacak) | >= 70% | PENDING |
| Backend (app/) | N/A | >= 80% | N/A (bu PR backend degisikligi icermiyor) |
| Agent (agent/) | N/A | >= 80% | N/A (bu PR agent degisikligi icermiyor) |

## Yazilan Testler

### iOS
| Test Dosyasi | Test Sayisi | Icerik |
|-------------|-------------|--------|
| `RafRafTests/Features/Approval/Data/ApprovalQuestionDTOTests.swift` | 4 | JSON decode testleri (full, null context, missing context, multi-option) |
| `RafRafTests/Features/Approval/Data/ApprovalQuestionDTOTests.swift` (ResponseDTO) | 3 | JSON encode testleri (basic, with note, roundtrip) |
| `RafRafTests/Features/Approval/Data/ApprovalMapperTests.swift` | 7 | DTO->Domain mapping (basic, styles, unknown category, unknown style, nil context, writeRemote, receivedAt) |
| `RafRafTests/Features/Approval/Domain/ApprovalModelTests.swift` | 9 | Domain model testleri (init, equatable, raw values, CaseIterable) |
| `RafRafTests/Features/Approval/Domain/SubmitApprovalDecisionUseCaseTests.swift` | 3 | UseCase testleri (approved, rejected with note, error) |
| `RafRafTests/Features/Approval/Presentation/ApprovalCardViewModelTests.swift` | 14 | ViewModel testleri (initial state, showQuestion, progress, dangerous category, submit, dismiss) |
| **Toplam** | **40** | |

## Mock Kullanimi

| Mock | Neden |
|------|-------|
| MockApprovalRepository | ApprovalRepositoryProtocol mock'u - WebSocket bagimliligini soyutlama |

## Edge Case'ler

- Bilinmeyen kategori: `destructive` olarak fallback
- Bilinmeyen option style: `secondary` olarak fallback
- Null context: Dogru isleniyor
- Bos context: Missing field decode testi
- Karar verilmis iken tekrar karar gondermeme
- Soru yokken karar gondermeme
- ApprovalDecision raw value dogrulama

## Kontrat Test Sonuclari

| Platform | Kontrat Dosyasi | Test Sayisi | Durum |
|----------|----------------|-------------|-------|
| iOS | approval-messages.json | 4 (DTO decode/encode) | PASS |

## Bilinen Sorunlar

- Coverage yuzdesi lokal ortamda hesaplanamadi (iOS simulator gerekli). CI'da xcodebuild test ile hesaplanacak.
- Countdown timer async testleri: Timer Task-based oldugu icin gercek zamanda test etmek CI'da yapilir. ViewModel state kontrolleri (remainingSeconds initial value, progressFraction) unit test ile dogrulandi.
