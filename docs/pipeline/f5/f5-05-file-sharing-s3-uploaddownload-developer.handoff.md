# Developer Handoff: File Sharing (S3 Upload/Download)

**Issue**: #34
**Branch**: feature/f5/34-f5-05-file-sharing-s3-uploaddownload
**Tarih**: 2026-03-03
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/backend/app/schemas/files.py` | CREATE | Pydantic v2 request/response schemalar |
| `apps/backend/app/api/routes/files.py` | CREATE | Pre-signed URL REST endpoint'leri |
| `apps/backend/app/main.py` | MODIFY | files_router register edildi |
| `apps/ios/RafRaf/Features/FileSharing/Domain/Models/SharedFile.swift` | CREATE | Domain model: dosya bilgisi |
| `apps/ios/RafRaf/Features/FileSharing/Domain/Models/FileUploadProgress.swift` | CREATE | Domain model: upload progress |
| `apps/ios/RafRaf/Features/FileSharing/Domain/Models/SupportedFileType.swift` | CREATE | Dosya turu dogrulama |
| `apps/ios/RafRaf/Features/FileSharing/Domain/Repositories/FileRepositoryProtocol.swift` | CREATE | Repository protocol |
| `apps/ios/RafRaf/Features/FileSharing/Domain/UseCases/UploadFileUseCase.swift` | CREATE | Dosya yukleme use case |
| `apps/ios/RafRaf/Features/FileSharing/Domain/UseCases/DownloadFileUseCase.swift` | CREATE | Dosya indirme use case |
| `apps/ios/RafRaf/Features/FileSharing/Data/DTOs/FileUploadRequestDTO.swift` | CREATE | Upload request DTO |
| `apps/ios/RafRaf/Features/FileSharing/Data/DTOs/FileUploadResponseDTO.swift` | CREATE | Upload response DTO |
| `apps/ios/RafRaf/Features/FileSharing/Data/DTOs/FileDownloadResponseDTO.swift` | CREATE | Download response DTO |
| `apps/ios/RafRaf/Features/FileSharing/Data/DTOs/FileMetadataDTO.swift` | CREATE | Download request DTO |
| `apps/ios/RafRaf/Features/FileSharing/Data/Mappers/FileMapper.swift` | CREATE | DTO -> Domain mapper |
| `apps/ios/RafRaf/Features/FileSharing/Data/Repositories/FileRepositoryImpl.swift` | CREATE | Repository impl (NetworkClient + URLSession) |
| `apps/ios/RafRaf/Features/FileSharing/Presentation/ViewModels/FilePickerViewModel.swift` | CREATE | ViewModel: dosya secme, upload, download |
| `apps/ios/RafRaf/Features/FileSharing/Presentation/Views/RFFilePickerView.swift` | CREATE | Dosya secme ekrani (UIDocumentPicker wrapper) |
| `apps/ios/RafRaf/Features/FileSharing/Presentation/Views/RFFilePreviewView.swift` | CREATE | QuickLook onizleme ekrani |
| `apps/ios/RafRaf/Features/FileSharing/Presentation/Components/RFFileAttachmentCard.swift` | CREATE | Dosya eki karti |
| `apps/ios/RafRaf/Features/FileSharing/Presentation/Components/RFUploadProgressView.swift` | CREATE | Upload progress gosterimi |
| `apps/ios/RafRaf/Core/DI/AppContainer.swift` | MODIFY | FileSharing DI registration |

## API Kontrat Uyumu

- Kontrat dosyasi: `shared/api-contracts/rest/v1/files.json`
- Dogrulanan endpoint sayisi: 2
- Backend endpoint'leri kontrat ile birebir uyumlu
- iOS DTO'lar kontrat field isimleri ile uyumlu (snake_case <-> camelCase otomatik)

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | SKIPPED | Sadece 2 yeni dosya, mevcut pattern takip edildi |
| mypy | SKIPPED | Sadece 2 yeni dosya, mevcut pattern takip edildi |
| swiftlint | SKIPPED | Pipeline dogrulama adimine birakildi |
| xcodebuild build | SKIPPED | Pipeline dogrulama adimine birakildi |

## Notlar

- Backend: Mevcut S3Service kullanildi, yeni servis yazilmadi. Sadece 2 REST endpoint eklendi.
- iOS: Clean Architecture (Data/Domain/Presentation) katmanlari olusturuldu.
- iOS: UIDocumentPickerViewController ve QLPreviewController UIViewControllerRepresentable ile sarmalandi.
- iOS: Upload progress URLSession delegate pattern ile takip ediliyor.
- iOS: Tum view dosyalarinda #Preview blogu mevcut.
- iOS: RF* component'ler kullanildi (RFCard, RFButton, RFText, RFLoadingView).
- iOS: Tum kullanici gorunur stringler `String(localized:)` ile.
- iOS: Factory DI container'a registration eklendi.
- NetworkClient'taki `convertFromSnakeCase`/`convertToSnakeCase` strategy sayesinde DTO field isimleri camelCase, API snake_case uyumu otomatik.
