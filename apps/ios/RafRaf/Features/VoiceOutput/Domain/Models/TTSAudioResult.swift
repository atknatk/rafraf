import Foundation

/// TTS ses sonucu domain modeli.
/// Backend'den donen ses verisini temsil eder.
struct TTSAudioResult: Sendable, Equatable {
    /// Ses verisi (MP3 formati).
    let audioData: Data
    /// Orijinal metin.
    let text: String
    /// Kullanilan ses.
    let voice: TTSVoice
    /// Toplam sure (saniye cinsinden, oynatma basladiktan sonra hesaplanir).
    let duration: TimeInterval?

    init(
        audioData: Data,
        text: String,
        voice: TTSVoice,
        duration: TimeInterval? = nil
    ) {
        self.audioData = audioData
        self.text = text
        self.voice = voice
        self.duration = duration
    }
}
