import Foundation

/// Dosya indirme use case.
/// S3'ten dosya indirme islemini yonetir.
struct DownloadFileUseCase: Sendable {
    private let repository: FileRepositoryProtocol

    init(repository: FileRepositoryProtocol) {
        self.repository = repository
    }

    /// Dosyayi S3'ten indirir ve lokal dosya URL'si dondurur.
    /// - Parameters:
    ///   - projectId: Proje ID'si.
    ///   - fileKey: S3 object key.
    /// - Returns: Indirilen dosyanin SharedFile domain modeli (localURL dolu).
    func execute(
        projectId: String,
        fileKey: String
    ) async throws -> SharedFile {
        try await repository.downloadFile(
            projectId: projectId,
            fileKey: fileKey
        )
    }
}
