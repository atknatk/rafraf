import Foundation
import Testing
@testable import RafRaf

/// TranscriptionMapper testleri.
@Suite("TranscriptionMapper Tests")
struct TranscriptionMapperTests {

    @Test("toDomain: gecerli interim DTO -> TranscriptionResult")
    func toDomainInterimResult() {
        let dto = VoiceInputTestFactory.makeDeepgramTranscriptDTO(
            transcript: "merhaba",
            isFinal: false,
            confidence: 0.85
        )

        let result = TranscriptionMapper.toDomain(from: dto, language: .turkish)

        #expect(result != nil)
        #expect(result?.text == "merhaba")
        #expect(result?.isFinal == false)
        #expect(result?.confidence == 0.85)
        #expect(result?.language == .turkish)
    }

    @Test("toDomain: gecerli final DTO -> TranscriptionResult")
    func toDomainFinalResult() {
        let dto = VoiceInputTestFactory.makeDeepgramTranscriptDTO(
            transcript: "Merhaba dunya.",
            isFinal: true,
            confidence: 0.95
        )

        let result = TranscriptionMapper.toDomain(from: dto, language: .english)

        #expect(result != nil)
        #expect(result?.text == "Merhaba dunya.")
        #expect(result?.isFinal == true)
        #expect(result?.confidence == 0.95)
        #expect(result?.language == .english)
    }

    @Test("toDomain: bos transkripsiyon -> nil")
    func toDomainEmptyTranscript() {
        let dto = VoiceInputTestFactory.makeEmptyDeepgramTranscriptDTO()

        let result = TranscriptionMapper.toDomain(from: dto, language: .turkish)

        #expect(result == nil)
    }

    @Test("toDomain: sadece whitespace transkripsiyon -> nil")
    func toDomainWhitespaceTranscript() {
        let dto = VoiceInputTestFactory.makeDeepgramTranscriptDTO(
            transcript: "   \n  "
        )

        let result = TranscriptionMapper.toDomain(from: dto, language: .turkish)

        #expect(result == nil)
    }

    @Test("toDomain: bos alternatives dizisi -> nil")
    func toDomainEmptyAlternatives() {
        let dto = DeepgramTranscriptDTO(
            type: "Results",
            channelIndex: nil,
            duration: nil,
            start: nil,
            isFinal: false,
            speechFinal: false,
            channel: DeepgramChannelDTO(alternatives: [])
        )

        let result = TranscriptionMapper.toDomain(from: dto, language: .turkish)

        #expect(result == nil)
    }

    @Test("toDomain: dil parametresi dogru atanmali")
    func toDomainLanguageAssignment() {
        let dto = VoiceInputTestFactory.makeDeepgramTranscriptDTO(transcript: "hello")

        let turkishResult = TranscriptionMapper.toDomain(from: dto, language: .turkish)
        let englishResult = TranscriptionMapper.toDomain(from: dto, language: .english)

        #expect(turkishResult?.language == .turkish)
        #expect(englishResult?.language == .english)
    }

    @Test("toDomain: transkripsiyon bosluk trim edilmeli")
    func toDomainTrimsWhitespace() {
        let dto = VoiceInputTestFactory.makeDeepgramTranscriptDTO(
            transcript: "  merhaba  "
        )

        let result = TranscriptionMapper.toDomain(from: dto, language: .turkish)

        #expect(result?.text == "merhaba")
    }
}
