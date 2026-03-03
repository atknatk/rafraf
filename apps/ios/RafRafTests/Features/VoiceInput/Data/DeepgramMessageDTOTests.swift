import Foundation
import Testing
@testable import RafRaf

/// DeepgramMessageDTO testleri.
@Suite("DeepgramMessageDTO Tests")
struct DeepgramMessageDTOTests {

    @Test("DeepgramTranscriptDTO JSON decode basarili olmali")
    func decodeTranscriptDTO() throws {
        let json = """
        {
            "type": "Results",
            "channel_index": [0, 1],
            "duration": 1.5,
            "start": 0.0,
            "is_final": true,
            "speech_final": true,
            "channel": {
                "alternatives": [
                    {
                        "transcript": "Merhaba dunya",
                        "confidence": 0.95,
                        "words": [
                            {
                                "word": "merhaba",
                                "start": 0.0,
                                "end": 0.5,
                                "confidence": 0.96,
                                "punctuated_word": "Merhaba"
                            },
                            {
                                "word": "dunya",
                                "start": 0.5,
                                "end": 1.0,
                                "confidence": 0.94,
                                "punctuated_word": "dunya"
                            }
                        ]
                    }
                ]
            }
        }
        """.data(using: .utf8)!

        let dto = try JSONDecoder().decode(DeepgramTranscriptDTO.self, from: json)

        #expect(dto.type == "Results")
        #expect(dto.isFinal == true)
        #expect(dto.speechFinal == true)
        #expect(dto.duration == 1.5)
        #expect(dto.channel.alternatives.count == 1)
        #expect(dto.channel.alternatives.first?.transcript == "Merhaba dunya")
        #expect(dto.channel.alternatives.first?.confidence == 0.95)
        #expect(dto.channel.alternatives.first?.words?.count == 2)
        #expect(dto.channel.alternatives.first?.words?.first?.punctuatedWord == "Merhaba")
    }

    @Test("DeepgramTranscriptDTO interim sonuc decode basarili olmali")
    func decodeInterimDTO() throws {
        let json = """
        {
            "type": "Results",
            "is_final": false,
            "speech_final": false,
            "channel": {
                "alternatives": [
                    {
                        "transcript": "merha",
                        "confidence": 0.70,
                        "words": null
                    }
                ]
            }
        }
        """.data(using: .utf8)!

        let dto = try JSONDecoder().decode(DeepgramTranscriptDTO.self, from: json)

        #expect(dto.isFinal == false)
        #expect(dto.speechFinal == false)
        #expect(dto.channelIndex == nil)
        #expect(dto.duration == nil)
        #expect(dto.channel.alternatives.first?.words == nil)
    }

    @Test("DeepgramCloseStreamDTO encode basarili olmali")
    func encodeCloseStream() throws {
        let dto = DeepgramCloseStreamDTO()
        let data = try JSONEncoder().encode(dto)
        let json = try JSONDecoder().decode([String: String].self, from: data)

        #expect(json["type"] == "CloseStream")
    }

    @Test("DeepgramMetadataDTO decode basarili olmali")
    func decodeMetadata() throws {
        let json = """
        {
            "type": "Metadata",
            "request_id": "abc-123",
            "model_info": {
                "name": "nova-2",
                "version": "2024-01-01"
            }
        }
        """.data(using: .utf8)!

        let dto = try JSONDecoder().decode(DeepgramMetadataDTO.self, from: json)

        #expect(dto.type == "Metadata")
        #expect(dto.requestId == "abc-123")
        #expect(dto.modelInfo?.name == "nova-2")
    }

    @Test("DeepgramWordDTO CodingKeys dogru calisir")
    func wordDTOCodingKeys() throws {
        let json = """
        {
            "word": "test",
            "start": 0.0,
            "end": 0.5,
            "confidence": 0.9,
            "punctuated_word": "Test"
        }
        """.data(using: .utf8)!

        let dto = try JSONDecoder().decode(DeepgramWordDTO.self, from: json)

        #expect(dto.word == "test")
        #expect(dto.punctuatedWord == "Test")
    }
}
