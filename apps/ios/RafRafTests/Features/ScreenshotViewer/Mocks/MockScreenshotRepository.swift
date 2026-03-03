import Foundation
@testable import RafRaf

/// Test icin mock screenshot repository.
final class MockScreenshotRepository: ScreenshotRepositoryProtocol, @unchecked Sendable {
    var fetchScreenshotResult: Result<Screenshot, Error> = .success(
        ScreenshotTestFactory.makeScreenshot()
    )
    var fetchScreenshotCallCount = 0
    var lastScreenshotId: String?

    var getPreSignedURLResult: Result<String, Error> = .success(
        "https://presigned.example.com/screenshot.png"
    )
    var getPreSignedURLCallCount = 0
    var lastOriginalURL: String?

    func fetchScreenshot(by screenshotId: String) async throws -> Screenshot {
        fetchScreenshotCallCount += 1
        lastScreenshotId = screenshotId
        return try fetchScreenshotResult.get()
    }

    func getPreSignedURL(for originalURL: String) async throws -> String {
        getPreSignedURLCallCount += 1
        lastOriginalURL = originalURL
        return try getPreSignedURLResult.get()
    }
}

/// Screenshot repository test hatalari.
enum ScreenshotRepositoryTestError: Error {
    case networkError
    case notFound
    case invalidURL
}
