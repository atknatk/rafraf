# Feature: File Sharing (S3 Upload/Download)

**Issue**: #34
**Faz**: F5
**Katmanlar**: backend | ios
**Pipeline**: full
**Tarih**: 2026-03-03

## Ozet

iOS uygulamasindan dosya yukleme, indirme ve onizleme ozelligi. Kullanici chat akisinda dosya ekleyebilir, backend pre-signed URL olusturur, iOS URLSession ile S3'e upload/download yapar. QuickLook ile dosya onizleme destegi saglar. Desteklenen formatlar: PDF, resim, metin ve kod dosyalari. Max dosya boyutu: 50MB.

## Degisecek Dosyalar

### Backend (`apps/backend/`)

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/api/routes/files.py` | CREATE | Pre-signed URL endpoint'leri (upload + download) |
| `app/schemas/files.py` | CREATE | Pydantic request/response schemalar |

### iOS (`apps/ios/`)

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `RafRaf/Features/FileSharing/Data/DTOs/FileUploadRequestDTO.swift` | CREATE | Upload pre-signed URL istek DTO |
| `RafRaf/Features/FileSharing/Data/DTOs/FileUploadResponseDTO.swift` | CREATE | Upload pre-signed URL yanit DTO |
| `RafRaf/Features/FileSharing/Data/DTOs/FileDownloadResponseDTO.swift` | CREATE | Download pre-signed URL yanit DTO |
| `RafRaf/Features/FileSharing/Data/DTOs/FileMetadataDTO.swift` | CREATE | Dosya metadata DTO |
| `RafRaf/Features/FileSharing/Data/Mappers/FileMapper.swift` | CREATE | DTO -> Domain model mapper |
| `RafRaf/Features/FileSharing/Data/Repositories/FileRepositoryImpl.swift` | CREATE | Dosya upload/download repository implementasyonu |
| `RafRaf/Features/FileSharing/Domain/Models/SharedFile.swift` | CREATE | Domain model: dosya bilgisi (id, name, size, type, url) |
| `RafRaf/Features/FileSharing/Domain/Models/FileUploadProgress.swift` | CREATE | Domain model: upload ilerleme durumu |
| `RafRaf/Features/FileSharing/Domain/Models/SupportedFileType.swift` | CREATE | Domain enum: desteklenen dosya turleri |
| `RafRaf/Features/FileSharing/Domain/Repositories/FileRepositoryProtocol.swift` | CREATE | Repository protocol |
| `RafRaf/Features/FileSharing/Domain/UseCases/UploadFileUseCase.swift` | CREATE | Dosya yukleme use case |
| `RafRaf/Features/FileSharing/Domain/UseCases/DownloadFileUseCase.swift` | CREATE | Dosya indirme use case |
| `RafRaf/Features/FileSharing/Presentation/ViewModels/FilePickerViewModel.swift` | CREATE | ViewModel: dosya secme, yukleme, ilerleme state |
| `RafRaf/Features/FileSharing/Presentation/Views/RFFilePickerView.swift` | CREATE | Dosya secme ekrani (UIDocumentPicker wrapper) |
| `RafRaf/Features/FileSharing/Presentation/Views/RFFilePreviewView.swift` | CREATE | QuickLook dosya onizleme ekrani |
| `RafRaf/Features/FileSharing/Presentation/Components/RFFileAttachmentCard.swift` | CREATE | Chat icinde dosya eki karti |
| `RafRaf/Features/FileSharing/Presentation/Components/RFUploadProgressView.swift` | CREATE | Upload ilerleme gosterimi |

## API Endpoints

### REST

| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| POST | `/api/v1/files/upload-url` | `FileUploadURLRequest` | `FileUploadURLResponse` | Pre-signed upload URL olusturma |
| POST | `/api/v1/files/download-url` | `FileDownloadURLRequest` | `FileDownloadURLResponse` | Pre-signed download URL olusturma |

## Data Model

### Pydantic Models

```python
class FileUploadURLRequest(BaseModel):
    """Pre-signed upload URL istegi."""
    project_id: str  # Proje ID
    file_name: str  # Dosya adi
    content_type: str  # MIME tipi
    file_size: int  # Dosya boyutu (bytes)

class FileUploadURLResponse(BaseModel):
    """Pre-signed upload URL yaniti."""
    model_config = ConfigDict(frozen=True)
    upload_url: str  # Pre-signed upload URL
    file_key: str  # S3 object key
    expiration_seconds: int  # URL gecerlilik suresi

class FileDownloadURLRequest(BaseModel):
    """Pre-signed download URL istegi."""
    project_id: str  # Proje ID
    file_key: str  # S3 object key

class FileDownloadURLResponse(BaseModel):
    """Pre-signed download URL yaniti."""
    model_config = ConfigDict(frozen=True)
    download_url: str  # Pre-signed download URL
    file_key: str  # S3 object key
    expiration_seconds: int  # URL gecerlilik suresi
```

### Swift Models

```swift
// Domain/Models/SharedFile.swift
struct SharedFile: Identifiable, Sendable, Equatable {
    let id: String           // Benzersiz dosya ID (UUID)
    let name: String         // Dosya adi
    let fileKey: String      // S3 object key
    let contentType: String  // MIME tipi
    let size: Int            // Dosya boyutu (bytes)
    let downloadURL: URL?    // Pre-signed download URL (indirildiyse)
    let localURL: URL?       // Lokal dosya URL (indirildiyse)
}

// Domain/Models/FileUploadProgress.swift
struct FileUploadProgress: Sendable, Equatable {
    let fileId: String        // Dosya ID
    let fileName: String      // Dosya adi
    let totalBytes: Int64     // Toplam boyut
    let uploadedBytes: Int64  // Yuklenen boyut
    let progress: Double      // 0.0 - 1.0 arasi ilerleme
    let isCompleted: Bool     // Yukleme tamamlandi mi
    let error: String?        // Hata mesaji (varsa)
}

// Domain/Models/SupportedFileType.swift
enum SupportedFileType: String, Sendable, CaseIterable {
    case pdf
    case image  // png, jpg, gif
    case text   // txt, md
    case code   // py, js, ts, swift
    case log    // log
    case archive // zip

    var maxSizeBytes: Int { ... }
    var allowedExtensions: [String] { ... }
    var mimeTypes: [String] { ... }
}
```

```swift
// Data/DTOs/FileUploadRequestDTO.swift
struct FileUploadRequestDTO: Codable, Sendable {
    let projectId: String
    let fileName: String
    let contentType: String
    let fileSize: Int
}

// Data/DTOs/FileUploadResponseDTO.swift
struct FileUploadResponseDTO: Codable, Sendable {
    let uploadUrl: String
    let fileKey: String
    let expirationSeconds: Int
}

// Data/DTOs/FileDownloadResponseDTO.swift
struct FileDownloadResponseDTO: Codable, Sendable {
    let downloadUrl: String
    let fileKey: String
    let expirationSeconds: Int
}
```

## Business Rules

1. Max dosya boyutu: 50MB. Asildigi durumda kullaniciya uyari gosterilir
2. Desteklenen formatlar: PDF (20MB), resim/png/jpg/gif (10MB), metin/txt/md (5MB), kod/py/js/ts/swift (5MB), log (10MB), arsiv/zip (50MB)
3. Upload akisi: iOS dosya secer -> Backend'den pre-signed URL alir -> URLSession ile S3'e PUT yapar -> Sonucu chat'e ekler
4. Download akisi: Backend pre-signed download URL gonderir -> iOS URLSession ile indirir -> QuickLook ile onizleme gosterir
5. Upload progress: URLSession delegate ile gercek zamanli ilerleme gosterilir
6. Dosya tipi dogrulama: Secilen dosyanin MIME tipi ve uzantisi desteklenen turler arasinda olmali
7. Pre-signed URL gecerliligi: 1 saat (3600 saniye)
8. UIDocumentPickerViewController ile dosya secimi
9. QLPreviewController ile dosya onizleme
10. Dosya indirildikten sonra gecici dizinde saklanir, QuickLook ile goruntulenir

## Test Requirements

### Backend
- [ ] Unit test: FileUploadURLRequest validation (boyut limiti, MIME tipi)
- [ ] Unit test: FileDownloadURLRequest validation
- [ ] Integration test: POST /api/v1/files/upload-url endpoint
- [ ] Integration test: POST /api/v1/files/download-url endpoint

### iOS
- [ ] Unit test: FilePickerViewModel - dosya secme ve validasyon
- [ ] Unit test: FilePickerViewModel - upload progress state
- [ ] Unit test: FilePickerViewModel - hata durumlari
- [ ] Unit test: FileMapper - DTO->Domain mapping
- [ ] Unit test: UploadFileUseCase - basari ve hata senaryolari
- [ ] Unit test: DownloadFileUseCase - basari ve hata senaryolari
- [ ] Unit test: SupportedFileType - max boyut ve uzanti kontrolu
- [ ] Unit test: FileUploadRequestDTO encoding
- [ ] Unit test: FileUploadResponseDTO decoding
- [ ] Unit test: FileDownloadResponseDTO decoding

## Acceptance Criteria

- [ ] Dosya secme (UIDocumentPickerViewController)
- [ ] Dosya yukleme (S3 pre-signed URL)
- [ ] Upload progress gosterimi
- [ ] Dosya indirme
- [ ] Dosya onizleme (QuickLook)
- [ ] Desteklenen formatlar: PDF, resim, metin, kod
- [ ] #Preview
- [ ] Unit testler yazildi
- [ ] Coverage >= 70%
