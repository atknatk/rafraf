import Foundation
import os

/// Screenshot repository implementasyonu.
/// NetworkClient ile backend'den screenshot verilerini cekmek icin kullanilir.
final class ScreenshotRepositoryImpl: ScreenshotRepositoryProtocol, @unchecked Sendable {
    private let networkClient: NetworkClient
    private let logger = AppLogger.logger(for: "ScreenshotViewer")

    init(networkClient: NetworkClient) {
        self.networkClient = networkClient
    }

    func fetchScreenshot(by screenshotId: String) async throws -> Screenshot {
        logger.info("Screenshot yukleniyor: \(screenshotId)")
        let dto: ScreenshotDTO = try await networkClient.get(
            path: "/screenshots/\(screenshotId)"
        )
        return ScreenshotMapper.toDomain(dto)
    }

    func getPreSignedURL(for originalURL: String) async throws -> String {
        logger.info("Pre-signed URL isteniyor")
        let response: PreSignedURLResponse = try await networkClient.post(
            path: "/screenshots/presign",
            body: PreSignedURLRequest(url: originalURL)
        )
        return response.preSignedUrl
    }
}

/// Pre-signed URL istegi.
private struct PreSignedURLRequest: Codable, Sendable {
    let url: String
}

/// Pre-signed URL yaniti.
private struct PreSignedURLResponse: Codable, Sendable {
    let preSignedUrl: String
}
