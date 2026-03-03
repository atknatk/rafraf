import Foundation

/// Ses kaydini durdurma use case'i.
/// Deepgram streaming'i durdurur ve kaynaklari serbest birakir.
struct StopVoiceRecordingUseCase: Sendable {
    private let repository: VoiceInputRepositoryProtocol

    init(repository: VoiceInputRepositoryProtocol) {
        self.repository = repository
    }

    /// Ses kaydini durdurur ve streaming'i sonlandirir.
    func execute() async {
        await repository.stopStreaming()
    }
}
