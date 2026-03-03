import Foundation
@testable import RafRaf

/// Screenshot test verisi fabrikasi.
enum ScreenshotTestFactory {

    /// Standart screenshot modeli olusturur.
    static func makeScreenshot(
        id: String = "test-screenshot-123",
        url: String = "https://example.com/screenshot.png",
        title: String? = "Test Screenshot",
        timestamp: Date = Date(),
        width: Int? = 1920,
        height: Int? = 1080
    ) -> Screenshot {
        Screenshot(
            id: id,
            url: url,
            title: title,
            timestamp: timestamp,
            width: width,
            height: height
        )
    }

    /// Screenshot DTO olusturur.
    static func makeScreenshotDTO(
        id: String = "test-screenshot-123",
        url: String = "https://example.com/screenshot.png",
        title: String? = "Test Screenshot",
        timestamp: String = "2026-03-03T10:00:00.000Z",
        width: Int? = 1920,
        height: Int? = 1080
    ) -> ScreenshotDTO {
        ScreenshotDTO(
            id: id,
            url: url,
            title: title,
            timestamp: timestamp,
            width: width,
            height: height
        )
    }

    /// Gecersiz URL'li screenshot olusturur.
    static func makeInvalidURLScreenshot() -> Screenshot {
        Screenshot(
            id: "invalid-url-screenshot",
            url: "not-a-valid-url",
            title: "Invalid"
        )
    }

    /// Basliksiz screenshot olusturur.
    static func makeScreenshotWithoutTitle() -> Screenshot {
        Screenshot(
            id: "no-title-screenshot",
            url: "https://example.com/screenshot.png",
            title: nil
        )
    }

    /// Boyut bilgisi olmayan screenshot olusturur.
    static func makeScreenshotWithoutDimensions() -> Screenshot {
        Screenshot(
            id: "no-dims-screenshot",
            url: "https://example.com/screenshot.png",
            title: "No Dimensions",
            width: nil,
            height: nil
        )
    }
}
