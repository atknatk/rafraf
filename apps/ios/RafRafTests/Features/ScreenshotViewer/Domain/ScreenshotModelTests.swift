import Foundation
import Testing
@testable import RafRaf

/// Screenshot domain model testleri.
@Suite("Screenshot Domain Model Tests")
struct ScreenshotModelTests {

    // MARK: - Screenshot Init

    @Test("Screenshot dogru olusturulmali")
    func screenshotInit() {
        let now = Date()
        let screenshot = Screenshot(
            id: "sc-123",
            url: "https://example.com/img.png",
            title: "Test",
            timestamp: now,
            width: 1920,
            height: 1080
        )

        #expect(screenshot.id == "sc-123")
        #expect(screenshot.url == "https://example.com/img.png")
        #expect(screenshot.title == "Test")
        #expect(screenshot.timestamp == now)
        #expect(screenshot.width == 1920)
        #expect(screenshot.height == 1080)
    }

    @Test("Screenshot varsayilan degerlerle olusturulmali")
    func screenshotDefaultValues() {
        let screenshot = Screenshot(url: "https://example.com/img.png")

        #expect(screenshot.url == "https://example.com/img.png")
        #expect(screenshot.title == nil)
        #expect(screenshot.width == nil)
        #expect(screenshot.height == nil)
        #expect(!screenshot.id.isEmpty)
    }

    @Test("Screenshot Equatable uyumlu olmali")
    func screenshotEquatable() {
        let now = Date()
        let s1 = Screenshot(
            id: "same-id", url: "https://a.com/img.png",
            title: "T", timestamp: now, width: 100, height: 100
        )
        let s2 = Screenshot(
            id: "same-id", url: "https://a.com/img.png",
            title: "T", timestamp: now, width: 100, height: 100
        )

        #expect(s1 == s2)
    }

    @Test("Screenshot farkli id ile farkli olmali")
    func screenshotNotEqual() {
        let now = Date()
        let s1 = Screenshot(
            id: "id-1", url: "https://a.com/img.png",
            timestamp: now
        )
        let s2 = Screenshot(
            id: "id-2", url: "https://a.com/img.png",
            timestamp: now
        )

        #expect(s1 != s2)
    }

    @Test("Screenshot Identifiable uyumlu olmali")
    func screenshotIdentifiable() {
        let screenshot = ScreenshotTestFactory.makeScreenshot(id: "unique-id")

        #expect(screenshot.id == "unique-id")
    }

    @Test("Screenshot opsiyonel alanlar nil olabilmeli")
    func screenshotOptionalFields() {
        let screenshot = ScreenshotTestFactory.makeScreenshotWithoutTitle()

        #expect(screenshot.title == nil)
    }

    @Test("Screenshot boyut bilgisi olmadan olusturulabilmeli")
    func screenshotWithoutDimensions() {
        let screenshot = ScreenshotTestFactory.makeScreenshotWithoutDimensions()

        #expect(screenshot.width == nil)
        #expect(screenshot.height == nil)
    }

    // MARK: - ScreenshotViewerState

    @Test("ScreenshotViewerState loading durumu dogru olmali")
    func viewerStateLoading() {
        let state = ScreenshotViewerState.loading

        #expect(state == .loading)
    }

    @Test("ScreenshotViewerState loaded durumu dogru olmali")
    func viewerStateLoaded() {
        let state = ScreenshotViewerState.loaded

        #expect(state == .loaded)
    }

    @Test("ScreenshotViewerState error durumu mesaj icermeli")
    func viewerStateError() {
        let state = ScreenshotViewerState.error("Bir hata olustu")

        #expect(state == .error("Bir hata olustu"))
    }

    @Test("ScreenshotViewerState farkli hata mesajlari farkli olmali")
    func viewerStateErrorNotEqual() {
        let state1 = ScreenshotViewerState.error("Hata 1")
        let state2 = ScreenshotViewerState.error("Hata 2")

        #expect(state1 != state2)
    }
}
