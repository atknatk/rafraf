import Foundation

/// Dosya yukleme use case.
/// Dosya dogrulama ve S3 upload islemlerini yonetir.
struct UploadFileUseCase: Sendable {
    private let repository: FileRepositoryProtocol

    init(repository: FileRepositoryProtocol) {
        self.repository = repository
    }

    /// Dosyayi dogrular ve S3'e yukler.
    /// - Parameters:
    ///   - fileURL: Lokal dosya URL'si.
    ///   - projectId: Proje ID'si.
    ///   - onProgress: Ilerleme callback (0.0 - 1.0).
    /// - Returns: Yuklenen dosyanin SharedFile domain modeli.
    func execute(
        fileURL: URL,
        projectId: String,
        onProgress: @Sendable @escaping (Double) -> Void
    ) async throws -> SharedFile {
        let fileName = fileURL.lastPathComponent
        let fileExtension = fileURL.pathExtension.lowercased()

        // Dosya boyutunu kontrol et
        let fileAttributes = try FileManager.default.attributesOfItem(atPath: fileURL.path)
        let fileSize = (fileAttributes[.size] as? Int) ?? 0

        // Dosya turunu ve boyutunu dogrula
        let validationResult = SupportedFileType.validate(
            fileSize: fileSize,
            extension: fileExtension
        )
        switch validationResult {
        case .success:
            break
        case .failure(let error):
            throw error
        }

        // MIME tipini belirle
        let contentType = mimeType(for: fileExtension)

        return try await repository.uploadFile(
            fileURL: fileURL,
            projectId: projectId,
            fileName: fileName,
            contentType: contentType,
            fileSize: fileSize,
            onProgress: onProgress
        )
    }

    /// Uzantidan MIME tipi belirler.
    private func mimeType(for extension_: String) -> String {
        switch extension_.lowercased() {
        case "pdf": "application/pdf"
        case "png": "image/png"
        case "jpg", "jpeg": "image/jpeg"
        case "gif": "image/gif"
        case "txt": "text/plain"
        case "md": "text/markdown"
        case "py": "text/x-python"
        case "js": "text/javascript"
        case "ts": "text/typescript"
        case "swift": "text/x-swift"
        case "log": "text/x-log"
        case "zip": "application/zip"
        default: "application/octet-stream"
        }
    }
}
