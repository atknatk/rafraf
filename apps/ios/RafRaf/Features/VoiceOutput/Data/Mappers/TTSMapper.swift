import Foundation

/// TTS model donusturuculeri.
/// Domain <-> DTO donusumleri.
enum TTSMapper {
    /// Domain TTSRequest'i DTO'ya donusturur.
    /// - Parameter request: Domain model.
    /// - Returns: API istek DTO'su.
    static func toDTO(from request: TTSRequest) -> TTSRequestDTO {
        TTSRequestDTO(
            text: request.text,
            voice: request.voice.rawValue,
            speed: request.speed
        )
    }

    /// Ses verisini domain modele donusturur.
    /// - Parameters:
    ///   - data: Ham ses verisi (MP3).
    ///   - request: Orijinal istek.
    /// - Returns: Domain ses sonucu modeli.
    static func toDomain(
        from data: Data,
        request: TTSRequest
    ) -> TTSAudioResult {
        TTSAudioResult(
            audioData: data,
            text: request.text,
            voice: request.voice
        )
    }
}
