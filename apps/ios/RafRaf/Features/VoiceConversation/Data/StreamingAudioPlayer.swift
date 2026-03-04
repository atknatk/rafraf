@preconcurrency import AVFoundation
import Foundation
import os

/// Streaming ses oynatici.
/// Base64 MP3 chunk'lari sirayla decode edip AVAudioPlayer ile oynatir.
/// Chunk gelir → kuyruga ekle → sirayla cal → sonraki chunk'a gec.
final class StreamingAudioPlayer: NSObject, @unchecked Sendable {
    private let logger = AppLogger.logger(for: "StreamingAudio")
    private let lock = NSLock()

    private var chunkQueue: [(Data, String)] = [] // (audioData, sentenceText)
    private var currentPlayer: AVAudioPlayer?
    private var isPlayingQueue: Bool = false
    private var isSessionActive: Bool = false

    /// Tum chunk'lar oynadi callback.
    var onAllChunksPlayed: (@Sendable () -> Void)?

    /// Oynatim durumu.
    var isPlaying: Bool {
        lock.withLock { isPlayingQueue }
    }

    // MARK: - Public

    /// Audio session'i streaming oynatim icin hazirlar.
    func prepareSession() {
        guard !isSessionActive else { return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, options: [.defaultToSpeaker, .allowBluetooth])
            try session.setActive(true)
            isSessionActive = true
            logger.info("Streaming audio session hazir")
        } catch {
            logger.error("Audio session hatasi: \(error.localizedDescription)")
        }
    }

    /// Base64 encoded MP3 chunk'i kuyruga ekler ve oynatima baslar.
    func enqueueChunk(base64Audio: String, sentenceText: String) {
        guard let audioData = Data(base64Encoded: base64Audio) else {
            logger.warning("Base64 decode basarisiz: \(sentenceText.prefix(30))")
            return
        }

        lock.lock()
        chunkQueue.append((audioData, sentenceText))
        let shouldStart = !isPlayingQueue
        lock.unlock()

        if shouldStart {
            prepareSession()
            playNext()
        }

        logger.debug("Chunk eklendi - kuyruk: \(chunkQueue.count), cumle: \(sentenceText.prefix(40))")
    }

    /// Oynatimi durdurur ve kuyrugu temizler.
    func stopAndClear() {
        lock.lock()
        currentPlayer?.stop()
        currentPlayer = nil
        chunkQueue.removeAll()
        isPlayingQueue = false
        lock.unlock()

        deactivateSession()
        logger.info("Streaming oynatim durduruldu ve kuyruk temizlendi")
    }

    // MARK: - Private

    private func playNext() {
        lock.lock()
        guard let (data, sentenceText) = chunkQueue.first else {
            isPlayingQueue = false
            lock.unlock()
            deactivateSession()
            onAllChunksPlayed?()
            return
        }
        chunkQueue.removeFirst()
        isPlayingQueue = true
        lock.unlock()

        do {
            let player = try AVAudioPlayer(data: data)
            player.delegate = self
            player.prepareToPlay()

            lock.lock()
            self.currentPlayer = player
            lock.unlock()

            logger.debug("Chunk oynatiliyor: \(sentenceText.prefix(40)) - sure: \(player.duration)s")
            player.play()
        } catch {
            logger.error("Chunk oynatma hatasi: \(error.localizedDescription)")
            // Sonraki chunk'a gec
            playNext()
        }
    }

    private func deactivateSession() {
        guard isSessionActive else { return }
        isSessionActive = false
        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        } catch {
            logger.warning("Audio session deaktif edilemedi: \(error.localizedDescription)")
        }
    }
}

// MARK: - AVAudioPlayerDelegate

extension StreamingAudioPlayer: AVAudioPlayerDelegate {
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        lock.lock()
        currentPlayer = nil
        lock.unlock()

        // Sonraki chunk'a gec
        playNext()
    }

    func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        logger.error("Chunk decode hatasi: \(error?.localizedDescription ?? "bilinmeyen")")
        lock.lock()
        currentPlayer = nil
        lock.unlock()

        // Sonraki chunk'a gec
        playNext()
    }
}
