import Foundation

/// TTS API istek DTO'su.
/// Backend'e gonderilecek ses sentezi istegi.
struct TTSRequestDTO: Codable, Sendable {
    /// Sentezlenecek metin.
    let text: String
    /// Kullanilacak ses ismi.
    let voice: String
    /// Oynatma hizi (0.25 - 4.0).
    let speed: Double

    enum CodingKeys: String, CodingKey {
        case text
        case voice
        case speed
    }
}
