import Foundation

/// Screenshot repository protokolu.
/// Domain katmaninda tanimlenir, Data katmaninda implement edilir.
protocol ScreenshotRepositoryProtocol: Sendable {
    /// Belirtilen URL'den screenshot detaylarini yukler.
    /// - Parameter screenshotId: Screenshot benzersiz kimlik numarasi.
    /// - Returns: Screenshot domain modeli.
    func fetchScreenshot(by screenshotId: String) async throws -> Screenshot

    /// Screenshot URL'si icin pre-signed URL olusturur.
    /// - Parameter originalURL: Orijinal S3 URL'si.
    /// - Returns: Pre-signed URL string.
    func getPreSignedURL(for originalURL: String) async throws -> String
}
