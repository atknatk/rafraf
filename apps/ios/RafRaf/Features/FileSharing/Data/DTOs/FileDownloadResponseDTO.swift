import Foundation

/// Pre-signed download URL yanit DTO.
/// Backend'den donen S3 download URL bilgisi.
struct FileDownloadResponseDTO: Codable, Sendable {
    /// S3 pre-signed download URL.
    let downloadUrl: String
    /// S3 object key.
    let fileKey: String
    /// URL gecerlilik suresi (saniye).
    let expirationSeconds: Int
}
