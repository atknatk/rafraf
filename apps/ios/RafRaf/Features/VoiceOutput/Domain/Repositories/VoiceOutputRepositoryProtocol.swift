import Foundation

/// Voice output repository protokolu.
/// TTS API ile ses sentezi ve cache yonetimi.
protocol VoiceOutputRepositoryProtocol: Sendable {
    /// Metin icin TTS ses sentezi yapar.
    /// - Parameter request: TTS istegi parametreleri.
    /// - Returns: Sentezlenmis ses verisi.
    func synthesizeSpeech(request: TTSRequest) async throws -> TTSAudioResult

    /// Cache'deki ses verisini dondurur (varsa).
    /// - Parameter text: Aranan metin.
    /// - Returns: Cache'deki ses verisi veya nil.
    func getCachedAudio(for text: String) async -> TTSAudioResult?

    /// Tum cache'i temizler.
    func clearCache() async
}
