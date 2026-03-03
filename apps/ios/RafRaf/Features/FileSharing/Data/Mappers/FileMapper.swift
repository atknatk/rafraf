import Foundation

/// Dosya DTO <-> Domain model mapper.
enum FileMapper {
    /// Upload response DTO'yu SharedFile domain modeline donusturur.
    /// - Parameters:
    ///   - dto: Upload response DTO.
    ///   - fileName: Orijinal dosya adi.
    ///   - contentType: MIME tipi.
    ///   - fileSize: Dosya boyutu (bytes).
    /// - Returns: SharedFile domain modeli.
    static func toDomain(
        from dto: FileUploadResponseDTO,
        fileName: String,
        contentType: String,
        fileSize: Int
    ) -> SharedFile {
        SharedFile(
            id: UUID().uuidString,
            name: fileName,
            fileKey: dto.fileKey,
            contentType: contentType,
            size: fileSize,
            downloadURL: nil,
            localURL: nil
        )
    }

    /// Download response DTO'yu SharedFile domain modeline donusturur.
    /// - Parameters:
    ///   - dto: Download response DTO.
    ///   - localURL: Indirilen dosyanin lokal URL'si.
    /// - Returns: SharedFile domain modeli.
    static func toDomain(
        from dto: FileDownloadResponseDTO,
        localURL: URL
    ) -> SharedFile {
        let fileName = (dto.fileKey as NSString).lastPathComponent

        // Content type'i dosya uzantisindan tahmin et
        let ext = (fileName as NSString).pathExtension.lowercased()
        let contentType = mimeType(for: ext)

        // Dosya boyutunu lokal dosyadan al
        let fileSize = (try? FileManager.default.attributesOfItem(atPath: localURL.path)[.size] as? Int) ?? 0

        return SharedFile(
            id: UUID().uuidString,
            name: fileName,
            fileKey: dto.fileKey,
            contentType: contentType,
            size: fileSize,
            downloadURL: URL(string: dto.downloadUrl),
            localURL: localURL
        )
    }

    /// Uzantidan MIME tipi belirler.
    private static func mimeType(for extension_: String) -> String {
        switch extension_ {
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
