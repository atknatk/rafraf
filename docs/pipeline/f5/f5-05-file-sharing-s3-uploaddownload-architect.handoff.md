# Architect Handoff: File Sharing (S3 Upload/Download)

**Issue**: #34
**Faz**: F5
**Tarih**: 2026-03-03
**Sonraki Agent**: developer

## Ozet

iOS'tan dosya yukleme, indirme ve onizleme ozelligi. Backend pre-signed URL endpoint'leri saglayacak (mevcut S3Service uzerinden). iOS tarafinda Clean Architecture ile dosya secme (UIDocumentPicker), upload/download (URLSession), progress gosterimi ve QuickLook onizleme implementasyonu yapilacak.

## Feature Spec

-> `shared/feature-specs/f5-34-f5-05-file-sharing-s3-uploaddownload.md`

## API Contracts

-> `shared/api-contracts/rest/v1/files.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 2 dosya (route + schema) |
| ios | HIGH | 17 dosya (Data + Domain + Presentation) |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- Backend'de mevcut `S3Service` (`app/services/s3_service.py`) kullanilacak. Yeni bir servis yazmaya gerek yok, sadece REST endpoint'ler eklenmeli.
- Backend'de mevcut `app/api/routes/` pattern'i takip edilmeli (projects.py ornegi).
- Backend main.py'de yeni router'in register edilmesi gerekiyor.
- iOS NetworkClient zaten `convertFromSnakeCase` ve `convertToSnakeCase` strategy kullaniyor, DTO'lar buna uygun tanimlanmali.
- iOS'ta dosya secimi icin UIDocumentPickerViewController UIViewControllerRepresentable ile SwiftUI'a sarmalanmali.
- QuickLook icin QLPreviewController UIViewControllerRepresentable ile kullanilmali.
- Upload progress icin URLSession delegate pattern kullanilmali.
- Max dosya boyutu: 50MB (business rule).
- iOS Core/Networking/NetworkClient.swift'te `put` methodu yok; upload icin dogrudan URLSession kullanilmali (pre-signed URL'e PUT istegi).
- Factory DI container'a (AppContainer.swift) yeni registration'lar eklenmeli.
- Mevcut RF* component'ler: RFButton, RFCard, RFText, RFTextField, RFAvatar, RFEmptyStateView, RFErrorView, RFLoadingView.
- Yeni RF* prefix'li component'ler: RFFileAttachmentCard, RFUploadProgressView, RFFilePickerView, RFFilePreviewView.

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi
