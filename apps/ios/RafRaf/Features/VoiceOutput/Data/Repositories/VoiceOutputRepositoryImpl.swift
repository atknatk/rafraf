import Foundation
import os

/// Voice output repository implementasyonu.
/// Backend TTS proxy endpoint'i ile ses sentezi ve cache yonetimi.
final class VoiceOutputRepositoryImpl: VoiceOutputRepositoryProtocol, @unchecked Sendable {
    private let networkClient: NetworkClient
    private let cache: TTSAudioCache
    private let logger = AppLogger.logger(for: "VoiceOutputRepository")

    /// TTS API endpoint yolu.
    private static let ttsEndpoint = "/api/v1/tts/synthesize"

    init(
        networkClient: NetworkClient,
        cache: TTSAudioCache = TTSAudioCache()
    ) {
        self.networkClient = networkClient
        self.cache = cache
    }

    // MARK: - VoiceOutputRepositoryProtocol

    func synthesizeSpeech(request: TTSRequest) async throws -> TTSAudioResult {
        // Cache kontrolu
        let cacheKey = buildCacheKey(text: request.text, voice: request.voice)
        if let cachedData = await cache.get(for: cacheKey) {
            logger.info("Cache'den ses verisi yuklendi - \(cachedData.count) bytes")
            return TTSMapper.toDomain(from: cachedData, request: request)
        }

        // Backend'e TTS istegi gonder
        let dto = TTSMapper.toDTO(from: request)

        do {
            let audioData: Data = try await networkClient.postRawData(
                path: Self.ttsEndpoint,
                body: dto
            )

            // Cache'e kaydet
            await cache.set(audioData, for: cacheKey)

            logger.info("TTS ses verisi alindi - \(audioData.count) bytes")
            return TTSMapper.toDomain(from: audioData, request: request)
        } catch {
            logger.error("TTS API hatasi: \(error.localizedDescription)")
            throw VoiceOutputRepositoryError.ttsRequestFailed
        }
    }

    func getCachedAudio(for text: String) async -> TTSAudioResult? {
        // Varsayilan ses ile cache'e bak
        let cacheKey = buildCacheKey(text: text, voice: .alloy)
        guard let cachedData = await cache.get(for: cacheKey) else {
            return nil
        }
        return TTSAudioResult(audioData: cachedData, text: text, voice: .alloy)
    }

    func clearCache() async {
        await cache.clearAll()
        logger.info("TTS cache temizlendi")
    }

    // MARK: - Private

    private func buildCacheKey(text: String, voice: TTSVoice) -> String {
        "\(voice.rawValue):\(text)"
    }
}

/// Voice output repository hatalari.
enum VoiceOutputRepositoryError: Error, Sendable {
    case ttsRequestFailed
}
