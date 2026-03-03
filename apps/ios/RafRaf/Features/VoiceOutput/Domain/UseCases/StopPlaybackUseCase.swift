import Foundation

/// Ses oynatma durdurma use case.
/// Aktif ses oynatmayini durdurur ve kaynaklari serbest birakir.
struct StopPlaybackUseCase: Sendable {
    private let audioPlayer: VoiceAudioPlayerProtocol

    init(audioPlayer: VoiceAudioPlayerProtocol) {
        self.audioPlayer = audioPlayer
    }

    /// Ses oynatmayi durdurur.
    func execute() {
        audioPlayer.stop()
    }
}

/// Ses oynatici protokolu.
/// Domain katmaninda tanimlanir, Data katmaninda implemente edilir.
protocol VoiceAudioPlayerProtocol: Sendable {
    /// Ses verisini oynatir.
    /// - Parameters:
    ///   - data: Oynatilacak ses verisi (MP3).
    ///   - speed: Oynatma hizi (0.25 - 4.0).
    func play(data: Data, speed: Float) async throws
    /// Oynatmayi duraklatir.
    func pause()
    /// Duraklatilmis oynatmayi devam ettirir.
    func resume()
    /// Oynatmayi durdurur.
    func stop()
    /// Oynatma durumu.
    var isPlaying: Bool { get }
    /// Duraklatilmis mi.
    var isPaused: Bool { get }
    /// Oynatma ilerlemesi (0.0 - 1.0).
    var progress: Double { get }
    /// Toplam sure (saniye).
    var duration: TimeInterval { get }
    /// Oynatma tamamlandi callback.
    var onPlaybackFinished: (@Sendable () -> Void)? { get set }
}
