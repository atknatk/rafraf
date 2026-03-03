import Foundation
import Testing
@testable import RafRaf

/// TTSRequestDTO testleri.
@Suite("TTSRequestDTO Tests")
struct TTSRequestDTOTests {

    @Test("DTO dogru olusturulabilmeli")
    func createDTO() {
        let dto = TTSRequestDTO(text: "Merhaba", voice: "alloy", speed: 1.0)

        #expect(dto.text == "Merhaba")
        #expect(dto.voice == "alloy")
        #expect(dto.speed == 1.0)
    }

    @Test("Codable: JSON encode dogru calisir")
    func jsonEncode() throws {
        let dto = VoiceOutputTestFactory.createRequestDTO(
            text: "Test",
            voice: "nova",
            speed: 1.5
        )
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase

        let data = try encoder.encode(dto)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]

        #expect(json?["text"] as? String == "Test")
        #expect(json?["voice"] as? String == "nova")
        #expect(json?["speed"] as? Double == 1.5)
    }

    @Test("Codable: JSON decode dogru calisir")
    func jsonDecode() throws {
        let json = """
        {"text":"Merhaba","voice":"shimmer","speed":2.0}
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let dto = try decoder.decode(TTSRequestDTO.self, from: json)

        #expect(dto.text == "Merhaba")
        #expect(dto.voice == "shimmer")
        #expect(dto.speed == 2.0)
    }

    @Test("Codable: round-trip encode/decode dogru calisir")
    func codableRoundTrip() throws {
        let original = VoiceOutputTestFactory.createRequestDTO(
            text: "Round trip test",
            voice: "fable",
            speed: 0.75
        )

        let encoder = JSONEncoder()
        let decoder = JSONDecoder()

        let data = try encoder.encode(original)
        let decoded = try decoder.decode(TTSRequestDTO.self, from: data)

        #expect(decoded.text == original.text)
        #expect(decoded.voice == original.voice)
        #expect(decoded.speed == original.speed)
    }

    @Test("Sendable uyumu")
    func sendableConformance() async {
        let dto = VoiceOutputTestFactory.createRequestDTO()

        let task = Task.detached { () -> TTSRequestDTO in
            return dto
        }

        let result = await task.value
        #expect(result.text == dto.text)
    }
}
