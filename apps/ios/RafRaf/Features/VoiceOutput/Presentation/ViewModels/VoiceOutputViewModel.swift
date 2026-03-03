import Foundation
import os

/// Voice output ViewModel.
/// TTS ses sentezi ve oynatma durumunu yonetir.
@Observable
@MainActor
final class VoiceOutputViewModel {
    // MARK: - State

    /// Oynatma durumu.
    private(set) var state: VoiceOutputState = .idle
    /// Hata mesaji.
    var errorMessage: String?
    /// Oynatma ilerlemesi (0.0 - 1.0).
    private(set) var playbackProgress: Double = 0
    /// Secili ses.
    var selectedVoice: TTSVoice {
        didSet {
            UserDefaults.standard.set(selectedVoice.rawValue, forKey: TTSVoice.storageKey)
        }
    }
    /// Oynatma hizi (0.25 - 4.0).
    var playbackSpeed: Double {
        didSet {
            let clamped = max(TTSRequest.minimumSpeed, min(playbackSpeed, TTSRequest.maximumSpeed))
            if playbackSpeed != clamped {
                playbackSpeed = clamped
            }
            UserDefaults.standard.set(playbackSpeed, forKey: "voiceOutput.playbackSpeed")
        }
    }
    /// Otomatik oynatma ayari.
    var autoPlayEnabled: Bool {
        didSet {
            UserDefaults.standard.set(autoPlayEnabled, forKey: "voiceOutput.autoPlay")
        }
    }

    // MARK: - Computed

    /// Ses oynatiliyor mu.
    var isPlaying: Bool {
        state == .playing
    }

    /// Ses duraklatilmis mi.
    var isPaused: Bool {
        state == .paused
    }

    /// Ses yukleniyor mu.
    var isLoading: Bool {
        state == .loading
    }

    /// Hata durumunda mi.
    var isErrorState: Bool {
        if case .error = state { return true }
        return false
    }

    // MARK: - Private

    private let synthesizeSpeechUseCase: SynthesizeSpeechUseCase
    private let audioPlayer: VoiceAudioPlayerProtocol
    private let logger = AppLogger.logger(for: "VoiceOutput")
    private var progressTimer: Timer?
    private var currentAudioResult: TTSAudioResult?

    // MARK: - Init

    init(
        synthesizeSpeechUseCase: SynthesizeSpeechUseCase,
        audioPlayer: VoiceAudioPlayerProtocol
    ) {
        self.synthesizeSpeechUseCase = synthesizeSpeechUseCase
        self.audioPlayer = audioPlayer

        // Kayitli tercihleri yukle
        if let savedVoice = UserDefaults.standard.string(forKey: TTSVoice.storageKey),
           let voice = TTSVoice(rawValue: savedVoice) {
            self.selectedVoice = voice
        } else {
            self.selectedVoice = .alloy
        }

        let savedSpeed = UserDefaults.standard.double(forKey: "voiceOutput.playbackSpeed")
        self.playbackSpeed = savedSpeed > 0 ? savedSpeed : TTSRequest.defaultSpeed

        self.autoPlayEnabled = UserDefaults.standard.bool(forKey: "voiceOutput.autoPlay")

        // Oynatma tamamlandi callback
        var mutablePlayer = audioPlayer
        mutablePlayer.onPlaybackFinished = { [weak self] in
            Task { @MainActor [weak self] in
                self?.handlePlaybackFinished()
            }
        }

        logger.info("VoiceOutputViewModel baslatildi")
    }

    // MARK: - Actions

    /// Metni sese donusturup oynatir.
    /// - Parameter text: Seslendirilecek metin.
    func speak(text: String) async {
        // Bos metin kontrolu
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else {
            state = .error(.emptyText)
            errorMessage = VoiceOutputError.emptyText.localizedMessage
            return
        }

        // Zaten oynatiliyorsa durdur
        if isPlaying || isPaused {
            stopPlayback()
        }

        state = .loading
        logger.info("TTS istegi baslatiliyor - metin uzunlugu: \(trimmedText.count)")

        let request = TTSRequest(
            text: trimmedText,
            voice: selectedVoice,
            speed: playbackSpeed
        )

        do {
            let result = try await synthesizeSpeechUseCase.execute(request: request)
            currentAudioResult = result

            // Ses oynat
            try await audioPlayer.play(data: result.audioData, speed: Float(playbackSpeed))
            state = .playing
            startProgressTimer()
            logger.info("Ses oynatma baslatildi")
        } catch is VoiceOutputUseCaseError {
            state = .error(.emptyText)
            errorMessage = VoiceOutputError.emptyText.localizedMessage
            logger.warning("TTS bos metin hatasi")
        } catch is VoiceOutputRepositoryError {
            state = .error(.ttsRequestFailed)
            errorMessage = VoiceOutputError.ttsRequestFailed.localizedMessage
            logger.error("TTS API hatasi")
        } catch is VoiceOutputPlaybackError {
            state = .error(.playbackFailed)
            errorMessage = VoiceOutputError.playbackFailed.localizedMessage
            logger.error("Ses oynatma hatasi")
        } catch {
            state = .error(.ttsRequestFailed)
            errorMessage = VoiceOutputError.ttsRequestFailed.localizedMessage
            logger.error("Beklenmeyen hata: \(error.localizedDescription)")
        }
    }

    /// Oynatmayi duraklatir.
    func pausePlayback() {
        guard isPlaying else { return }
        audioPlayer.pause()
        state = .paused
        stopProgressTimer()
        logger.info("Oynatma duraklatildi")
    }

    /// Duraklatilmis oynatmayi devam ettirir.
    func resumePlayback() {
        guard isPaused else { return }
        audioPlayer.resume()
        state = .playing
        startProgressTimer()
        logger.info("Oynatma devam ettirildi")
    }

    /// Oynatmayi durdurur.
    func stopPlayback() {
        audioPlayer.stop()
        state = .idle
        playbackProgress = 0
        currentAudioResult = nil
        stopProgressTimer()
        logger.info("Oynatma durduruldu")
    }

    /// Ses secimi degistirir.
    /// - Parameter voice: Yeni ses secimi.
    func changeVoice(_ voice: TTSVoice) {
        selectedVoice = voice
        logger.info("Ses degistirildi: \(voice.rawValue)")
    }

    /// Hata mesajini temizler.
    func dismissError() {
        errorMessage = nil
        state = .idle
    }

    /// Otomatik oynatma icin cagrilir.
    /// - Parameter text: Seslendirilecek metin.
    func autoPlayIfEnabled(text: String) async {
        guard autoPlayEnabled else { return }
        await speak(text: text)
    }

    // MARK: - Private

    private func handlePlaybackFinished() {
        state = .idle
        playbackProgress = 0
        currentAudioResult = nil
        stopProgressTimer()
        logger.info("Oynatma tamamlandi")
    }

    private func startProgressTimer() {
        stopProgressTimer()
        progressTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.updateProgress()
            }
        }
    }

    private func stopProgressTimer() {
        progressTimer?.invalidate()
        progressTimer = nil
    }

    private func updateProgress() {
        playbackProgress = audioPlayer.progress
    }
}
