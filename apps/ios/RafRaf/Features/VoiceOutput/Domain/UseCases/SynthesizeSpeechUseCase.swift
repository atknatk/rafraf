import Foundation

/// Ses sentezi use case.
/// Metni sese donusturur; once cache'e bakar, yoksa API'den alir.
struct SynthesizeSpeechUseCase: Sendable {
    private let repository: VoiceOutputRepositoryProtocol

    init(repository: VoiceOutputRepositoryProtocol) {
        self.repository = repository
    }

    /// Metin icin ses sentezi yapar.
    /// - Parameter request: TTS istegi parametreleri.
    /// - Returns: Sentezlenmis ses verisi.
    func execute(request: TTSRequest) async throws -> TTSAudioResult {
        // Bos metin kontrolu
        let trimmed = request.text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            throw VoiceOutputUseCaseError.emptyText
        }

        // Oncelikle cache'e bak
        if let cached = await repository.getCachedAudio(for: request.text) {
            return cached
        }

        // Cache'de yoksa API'den al
        return try await repository.synthesizeSpeech(request: request)
    }
}

/// Use case hatalari.
enum VoiceOutputUseCaseError: Error, Sendable {
    case emptyText
}
