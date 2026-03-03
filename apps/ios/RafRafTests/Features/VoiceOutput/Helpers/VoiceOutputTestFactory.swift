import Foundation
@testable import RafRaf

/// Voice output test data factory.
enum VoiceOutputTestFactory {
    /// Test icin TTSRequest olusturur.
    static func createRequest(
        text: String = "Test mesaji",
        voice: TTSVoice = .alloy,
        speed: Double = 1.0
    ) -> TTSRequest {
        TTSRequest(text: text, voice: voice, speed: speed)
    }

    /// Test icin TTSAudioResult olusturur.
    static func createAudioResult(
        text: String = "Test mesaji",
        voice: TTSVoice = .alloy,
        dataSize: Int = 1024,
        duration: TimeInterval? = 3.0
    ) -> TTSAudioResult {
        let data = Data(repeating: 0xFF, count: dataSize)
        return TTSAudioResult(
            audioData: data,
            text: text,
            voice: voice,
            duration: duration
        )
    }

    /// Test icin TTSRequestDTO olusturur.
    static func createRequestDTO(
        text: String = "Test mesaji",
        voice: String = "alloy",
        speed: Double = 1.0
    ) -> TTSRequestDTO {
        TTSRequestDTO(text: text, voice: voice, speed: speed)
    }

    /// Bos ses verisi.
    static var emptyAudioData: Data {
        Data()
    }

    /// Buyuk ses verisi (1MB).
    static var largeAudioData: Data {
        Data(repeating: 0xAB, count: 1024 * 1024)
    }
}
