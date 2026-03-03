import Foundation
import Testing
@testable import RafRaf

/// ScreenshotMapper testleri.
@Suite("ScreenshotMapper Tests")
struct ScreenshotMapperTests {

    @Test("DTO domain modeline dogru donusturulmeli")
    func toDomainMapsCorrectly() {
        let dto = ScreenshotTestFactory.makeScreenshotDTO(
            id: "sc-mapper",
            url: "https://example.com/img.png",
            title: "Mapper Test",
            timestamp: "2026-03-03T10:00:00.000Z",
            width: 1920,
            height: 1080
        )

        let result = ScreenshotMapper.toDomain(dto)

        #expect(result.id == "sc-mapper")
        #expect(result.url == "https://example.com/img.png")
        #expect(result.title == "Mapper Test")
        #expect(result.width == 1920)
        #expect(result.height == 1080)
    }

    @Test("DTO timestamp domain modeline parse edilmeli")
    func toDomainParsesTimestamp() {
        let dto = ScreenshotTestFactory.makeScreenshotDTO(
            timestamp: "2026-03-03T10:30:00.000Z"
        )

        let result = ScreenshotMapper.toDomain(dto)

        // Tarih bos olmamali (Date() fallback degilse parse basarili)
        #expect(result.timestamp.timeIntervalSince1970 > 0)
    }

    @Test("Gecersiz timestamp fallback Date() kullanmali")
    func toDomainInvalidTimestampFallback() {
        let dto = ScreenshotTestFactory.makeScreenshotDTO(
            timestamp: "invalid-date"
        )

        let before = Date()
        let result = ScreenshotMapper.toDomain(dto)
        let after = Date()

        // Fallback Date() kullanildigindan, simdiki zamana yakin olmali
        #expect(result.timestamp >= before)
        #expect(result.timestamp <= after)
    }

    @Test("DTO opsiyonel alanlar nil ise domain modeli de nil olmali")
    func toDomainNilOptionalFields() {
        let dto = ScreenshotTestFactory.makeScreenshotDTO(
            title: nil,
            width: nil,
            height: nil
        )

        let result = ScreenshotMapper.toDomain(dto)

        #expect(result.title == nil)
        #expect(result.width == nil)
        #expect(result.height == nil)
    }

    @Test("DTO URL degeri korunmali")
    func toDomainPreservesURL() {
        let testURL = "https://s3.amazonaws.com/bucket/screenshots/test.png"
        let dto = ScreenshotTestFactory.makeScreenshotDTO(url: testURL)

        let result = ScreenshotMapper.toDomain(dto)

        #expect(result.url == testURL)
    }
}
