import Foundation

/// Ses kaydini baslatma use case'i.
/// Mikrofon izni kontrolu, Deepgram baglanti kurulumu ve ses streaming baslatma.
struct StartVoiceRecordingUseCase: Sendable {
    private let repository: VoiceInputRepositoryProtocol

    init(repository: VoiceInputRepositoryProtocol) {
        self.repository = repository
    }

    /// Ses kaydini baslatir ve transkripsiyon sonuclarini dondurur.
    /// - Parameter language: Hedef transkripsiyon dili.
    /// - Returns: Transkripsiyon sonuclarini yayan AsyncStream.
    /// - Throws: Baglanti veya izin hatasi.
    func execute(language: VoiceLanguage) async throws -> AsyncStream<TranscriptionResult> {
        try await repository.startStreaming(language: language)
    }
}
