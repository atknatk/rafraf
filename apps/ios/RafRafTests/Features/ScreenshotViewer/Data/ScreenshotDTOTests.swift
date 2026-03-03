import Foundation
import Testing
@testable import RafRaf

/// ScreenshotDTO testleri.
@Suite("ScreenshotDTO Tests")
struct ScreenshotDTOTests {

    @Test("ScreenshotDTO Codable encode/decode dogru olmali")
    func codableRoundTrip() throws {
        let dto = ScreenshotTestFactory.makeScreenshotDTO()

        let encoder = JSONEncoder()
        let data = try encoder.encode(dto)
        let decoder = JSONDecoder()
        let decoded = try decoder.decode(ScreenshotDTO.self, from: data)

        #expect(decoded.id == dto.id)
        #expect(decoded.url == dto.url)
        #expect(decoded.title == dto.title)
        #expect(decoded.timestamp == dto.timestamp)
        #expect(decoded.width == dto.width)
        #expect(decoded.height == dto.height)
    }

    @Test("ScreenshotDTO opsiyonel alanlar nil olabilmeli")
    func optionalFields() throws {
        let dto = ScreenshotTestFactory.makeScreenshotDTO(
            title: nil,
            width: nil,
            height: nil
        )

        let encoder = JSONEncoder()
        let data = try encoder.encode(dto)
        let decoder = JSONDecoder()
        let decoded = try decoder.decode(ScreenshotDTO.self, from: data)

        #expect(decoded.title == nil)
        #expect(decoded.width == nil)
        #expect(decoded.height == nil)
    }

    @Test("ScreenshotDTO JSON'dan decode edilebilmeli")
    func decodeFromJSON() throws {
        let json = """
        {
            "id": "sc-json-test",
            "url": "https://example.com/test.png",
            "title": "JSON Test",
            "timestamp": "2026-03-03T10:00:00.000Z",
            "width": 800,
            "height": 600
        }
        """
        let data = Data(json.utf8)
        let decoder = JSONDecoder()
        let dto = try decoder.decode(ScreenshotDTO.self, from: data)

        #expect(dto.id == "sc-json-test")
        #expect(dto.url == "https://example.com/test.png")
        #expect(dto.title == "JSON Test")
        #expect(dto.width == 800)
        #expect(dto.height == 600)
    }

    @Test("ScreenshotDTO opsiyonel alansiz JSON'dan decode edilebilmeli")
    func decodeFromJSONWithoutOptionals() throws {
        let json = """
        {
            "id": "sc-no-optional",
            "url": "https://example.com/test.png",
            "title": null,
            "timestamp": "2026-03-03T10:00:00.000Z",
            "width": null,
            "height": null
        }
        """
        let data = Data(json.utf8)
        let decoder = JSONDecoder()
        let dto = try decoder.decode(ScreenshotDTO.self, from: data)

        #expect(dto.id == "sc-no-optional")
        #expect(dto.title == nil)
        #expect(dto.width == nil)
        #expect(dto.height == nil)
    }
}
