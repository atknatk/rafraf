import Foundation

/// Pre-signed upload URL yanit DTO.
/// Backend'den donen S3 upload URL bilgisi.
struct FileUploadResponseDTO: Codable, Sendable {
    /// S3 pre-signed upload URL.
    let uploadUrl: String
    /// S3 object key (download isteklerinde kullanilir).
    let fileKey: String
    /// URL gecerlilik suresi (saniye).
    let expirationSeconds: Int
}
