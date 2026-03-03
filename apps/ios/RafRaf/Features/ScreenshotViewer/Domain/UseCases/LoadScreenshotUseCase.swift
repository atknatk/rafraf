import Foundation

/// Screenshot yukleme use case.
/// Repository'den screenshot bilgilerini alir.
struct LoadScreenshotUseCase: Sendable {
    private let repository: ScreenshotRepositoryProtocol

    init(repository: ScreenshotRepositoryProtocol) {
        self.repository = repository
    }

    /// Belirtilen ID'ye sahip screenshot'i yukler.
    /// - Parameter screenshotId: Screenshot benzersiz kimlik numarasi.
    /// - Returns: Screenshot domain modeli.
    func execute(screenshotId: String) async throws -> Screenshot {
        try await repository.fetchScreenshot(by: screenshotId)
    }
}
