import Foundation
@testable import RafRaf

/// Test icin mock voice input repository.
final class MockVoiceInputRepository: VoiceInputRepositoryProtocol, @unchecked Sendable {
    var isConnected: Bool = false

    var startStreamingResult: Result<AsyncStream<TranscriptionResult>, Error> = .success(
        AsyncStream { _ in }
    )
    var startStreamingCallCount = 0
    var lastLanguage: VoiceLanguage?

    var stopStreamingCallCount = 0

    /// Kontrollu stream icin continuation.
    var streamContinuation: AsyncStream<TranscriptionResult>.Continuation?

    func startStreaming(language: VoiceLanguage) async throws -> AsyncStream<TranscriptionResult> {
        startStreamingCallCount += 1
        lastLanguage = language
        isConnected = true

        switch startStreamingResult {
        case .success(let stream):
            return stream
        case .failure(let error):
            throw error
        }
    }

    func stopStreaming() async {
        stopStreamingCallCount += 1
        isConnected = false
        streamContinuation?.finish()
    }

    /// Kontrollu stream olusturur ve continuation'i saklar.
    func makeControllableStream() -> AsyncStream<TranscriptionResult> {
        AsyncStream { [weak self] continuation in
            self?.streamContinuation = continuation
        }
    }
}
