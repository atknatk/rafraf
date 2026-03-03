import Foundation
@testable import RafRaf

/// VoiceInput test data factory.
enum VoiceInputTestFactory {
    /// Ornek TranscriptionResult olusturur.
    static func makeTranscriptionResult(
        text: String = "Merhaba dunya",
        isFinal: Bool = false,
        confidence: Double = 0.95,
        language: VoiceLanguage = .turkish
    ) -> TranscriptionResult {
        TranscriptionResult(
            text: text,
            isFinal: isFinal,
            confidence: confidence,
            language: language
        )
    }

    /// Ornek AudioLevel olusturur.
    static func makeAudioLevel(
        averagePower: Float = -20.0,
        peakPower: Float = -10.0
    ) -> AudioLevel {
        AudioLevel(
            averagePower: averagePower,
            peakPower: peakPower,
            normalizedLevel: AudioLevel.normalize(decibels: averagePower)
        )
    }

    /// Ornek DeepgramTranscriptDTO olusturur.
    static func makeDeepgramTranscriptDTO(
        transcript: String = "test transcript",
        isFinal: Bool = false,
        confidence: Double = 0.92,
        speechFinal: Bool = false
    ) -> DeepgramTranscriptDTO {
        DeepgramTranscriptDTO(
            type: "Results",
            channelIndex: [0, 1],
            duration: 1.5,
            start: 0.0,
            isFinal: isFinal,
            speechFinal: speechFinal,
            channel: DeepgramChannelDTO(
                alternatives: [
                    DeepgramAlternativeDTO(
                        transcript: transcript,
                        confidence: confidence,
                        words: [
                            DeepgramWordDTO(
                                word: "test",
                                start: 0.0,
                                end: 0.5,
                                confidence: 0.95,
                                punctuatedWord: "Test"
                            )
                        ]
                    )
                ]
            )
        )
    }

    /// Bos transkripsiyon ile DeepgramTranscriptDTO.
    static func makeEmptyDeepgramTranscriptDTO() -> DeepgramTranscriptDTO {
        DeepgramTranscriptDTO(
            type: "Results",
            channelIndex: [0, 1],
            duration: 1.0,
            start: 0.0,
            isFinal: false,
            speechFinal: false,
            channel: DeepgramChannelDTO(
                alternatives: [
                    DeepgramAlternativeDTO(
                        transcript: "",
                        confidence: 0.0,
                        words: nil
                    )
                ]
            )
        )
    }
}
