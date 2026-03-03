import Foundation

/// Dosya paylasimi repository protokolu.
/// Data katmanindaki S3 upload/download islemlerini soyutlar.
protocol FileRepositoryProtocol: Sendable {
    /// Pre-signed upload URL alir ve dosyayi S3'e yukler.
    /// - Parameters:
    ///   - fileURL: Lokal dosya URL'si.
    ///   - projectId: Proje ID'si.
    ///   - fileName: Dosya adi.
    ///   - contentType: MIME tipi.
    ///   - fileSize: Dosya boyutu (bytes).
    ///   - onProgress: Ilerleme callback (0.0 - 1.0).
    /// - Returns: Yuklenen dosyanin SharedFile domain modeli.
    func uploadFile(
        fileURL: URL,
        projectId: String,
        fileName: String,
        contentType: String,
        fileSize: Int,
        onProgress: @Sendable @escaping (Double) -> Void
    ) async throws -> SharedFile

    /// Pre-signed download URL alir ve dosyayi indirir.
    /// - Parameters:
    ///   - projectId: Proje ID'si.
    ///   - fileKey: S3 object key.
    /// - Returns: Indirilen dosyanin lokal URL'si ile guncellenmis SharedFile.
    func downloadFile(
        projectId: String,
        fileKey: String
    ) async throws -> SharedFile
}
