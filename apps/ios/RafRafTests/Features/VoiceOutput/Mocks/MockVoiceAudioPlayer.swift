import Foundation
@testable import RafRaf

/// Test icin mock ses oynatici.
final class MockVoiceAudioPlayer: VoiceAudioPlayerProtocol, @unchecked Sendable {
    var onPlaybackFinished: (@Sendable () -> Void)?

    var playCallCount = 0
    var pauseCallCount = 0
    var resumeCallCount = 0
    var stopCallCount = 0

    var lastPlayData: Data?
    var lastPlaySpeed: Float?
    var shouldThrowOnPlay = false

    private var _isPlaying = false
    private var _isPaused = false
    private var _progress: Double = 0
    private var _duration: TimeInterval = 30.0

    var isPlaying: Bool { _isPlaying }
    var isPaused: Bool { _isPaused }
    var progress: Double { _progress }
    var duration: TimeInterval { _duration }

    func play(data: Data, speed: Float) async throws {
        playCallCount += 1
        lastPlayData = data
        lastPlaySpeed = speed

        if shouldThrowOnPlay {
            throw VoiceOutputPlaybackError.playbackInitFailed
        }

        _isPlaying = true
        _isPaused = false
    }

    func pause() {
        pauseCallCount += 1
        _isPlaying = false
        _isPaused = true
    }

    func resume() {
        resumeCallCount += 1
        _isPlaying = true
        _isPaused = false
    }

    func stop() {
        stopCallCount += 1
        _isPlaying = false
        _isPaused = false
        _progress = 0
    }

    // MARK: - Test Helpers

    /// Oynatma tamamlandi simulasyonu.
    func simulatePlaybackFinished() {
        _isPlaying = false
        _isPaused = false
        _progress = 0
        onPlaybackFinished?()
    }

    /// Ilerleme guncelleme simulasyonu.
    func setProgress(_ value: Double) {
        _progress = value
    }

    /// Sure ayarlama.
    func setDuration(_ value: TimeInterval) {
        _duration = value
    }
}
