import Foundation

/// Paylasilan dosya domain modeli.
/// Upload/download islemlerinde dosya bilgisini temsil eder.
struct SharedFile: Identifiable, Sendable, Equatable {
    /// Benzersiz dosya ID'si (UUID).
    let id: String
    /// Dosya adi (uzanti dahil).
    let name: String
    /// S3 object key.
    let fileKey: String
    /// MIME tipi.
    let contentType: String
    /// Dosya boyutu (bytes).
    let size: Int
    /// Pre-signed download URL (varsa).
    let downloadURL: URL?
    /// Lokal dosya URL (indirildiyse).
    let localURL: URL?
}
