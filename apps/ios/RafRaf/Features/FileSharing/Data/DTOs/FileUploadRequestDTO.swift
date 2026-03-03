import Foundation

/// Pre-signed upload URL istek DTO.
/// Backend'e gonderilen dosya yukleme URL istegi.
struct FileUploadRequestDTO: Codable, Sendable {
    /// Proje ID'si.
    let projectId: String
    /// Dosya adi (uzanti dahil).
    let fileName: String
    /// MIME tipi.
    let contentType: String
    /// Dosya boyutu (bytes).
    let fileSize: Int
}
