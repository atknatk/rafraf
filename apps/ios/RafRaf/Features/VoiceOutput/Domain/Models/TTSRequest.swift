import Foundation

/// TTS istegi domain modeli.
/// Backend'e gonderilecek ses sentezi isteginin parametrelerini icerir.
struct TTSRequest: Sendable, Equatable {
    /// Sentezlenecek metin.
    let text: String
    /// Kullanilacak ses.
    let voice: TTSVoice
    /// Oynatma hizi (0.25 - 4.0).
    let speed: Double

    /// Varsayilan hiz.
    static let defaultSpeed: Double = 1.0
    /// Minimum hiz.
    static let minimumSpeed: Double = 0.25
    /// Maksimum hiz.
    static let maximumSpeed: Double = 4.0
}
