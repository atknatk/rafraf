@preconcurrency import AVFoundation
import Foundation
import os

/// AVAudioPlayer tabanli ses oynatici.
/// TTS ses verisini oynatma, duraklatma, devam ettirme ve durdurma islemleri.
final class VoiceAudioPlayer: NSObject, VoiceAudioPlayerProtocol, @unchecked Sendable {
    private var audioPlayer: AVAudioPlayer?
    private let logger = AppLogger.logger(for: "VoiceAudioPlayer")
    private let lock = NSLock()

    // MARK: - VoiceAudioPlayerProtocol

    var onPlaybackFinished: (@Sendable () -> Void)?

    var isPlaying: Bool {
        lock.lock()
        defer { lock.unlock() }
        return audioPlayer?.isPlaying ?? false
    }

    var isPaused: Bool {
        lock.lock()
        defer { lock.unlock() }
        guard let player = audioPlayer else { return false }
        return !player.isPlaying && player.currentTime > 0
    }

    var progress: Double {
        lock.lock()
        defer { lock.unlock() }
        guard let player = audioPlayer, player.duration > 0 else { return 0 }
        return player.currentTime / player.duration
    }

    var duration: TimeInterval {
        lock.lock()
        defer { lock.unlock() }
        return audioPlayer?.duration ?? 0
    }

    func play(data: Data, speed: Float) async throws {
        try await MainActor.run {
            // AVAudioSession yapilandir
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, options: [.duckOthers])
            try session.setActive(true)
        }

        try initializeAndPlay(data: data, speed: speed)
    }

    func pause() {
        lock.lock()
        defer { lock.unlock() }
        audioPlayer?.pause()
        logger.info("Ses oynatma duraklatildi")
    }

    func resume() {
        lock.lock()
        defer { lock.unlock() }
        audioPlayer?.play()
        logger.info("Ses oynatma devam ettirildi")
    }

    func stop() {
        lock.lock()
        audioPlayer?.stop()
        audioPlayer = nil
        lock.unlock()

        deactivateAudioSession()
        logger.info("Ses oynatma durduruldu")
    }

    // MARK: - Private

    /// Ses oynaticiyi olusturur ve baslatir (senkron - lock guvenli).
    private func initializeAndPlay(data: Data, speed: Float) throws {
        lock.lock()
        do {
            let player = try AVAudioPlayer(data: data)
            player.delegate = self
            player.enableRate = true
            player.rate = max(0.5, min(speed, 2.0)) // AVAudioPlayer rate limiti: 0.5-2.0
            player.prepareToPlay()
            self.audioPlayer = player
            lock.unlock()

            logger.info("Ses oynatma baslatiliyor - sure: \(player.duration)s, hiz: \(speed)")
            player.play()
        } catch {
            lock.unlock()
            logger.error("Ses oynatma hatasi: \(error.localizedDescription)")
            throw VoiceOutputPlaybackError.playbackInitFailed
        }
    }

    private func deactivateAudioSession() {
        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        } catch {
            logger.warning("AVAudioSession deaktif edilemedi: \(error.localizedDescription)")
        }
    }
}

// MARK: - AVAudioPlayerDelegate

extension VoiceAudioPlayer: AVAudioPlayerDelegate {
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        lock.lock()
        audioPlayer = nil
        lock.unlock()

        deactivateAudioSession()
        logger.info("Ses oynatma tamamlandi - basarili: \(flag)")
        onPlaybackFinished?()
    }

    func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        lock.lock()
        audioPlayer = nil
        lock.unlock()

        deactivateAudioSession()
        logger.error("Ses decode hatasi: \(error?.localizedDescription ?? "bilinmeyen")")
        onPlaybackFinished?()
    }
}

/// Ses oynatma hatalari.
enum VoiceOutputPlaybackError: Error, Sendable {
    case playbackInitFailed
}
