import Foundation

/// Dosya download URL istegi DTO.
/// Backend'e gonderilen download URL istegi.
struct FileDownloadRequestDTO: Codable, Sendable {
    /// Proje ID'si.
    let projectId: String
    /// S3 object key.
    let fileKey: String
}
