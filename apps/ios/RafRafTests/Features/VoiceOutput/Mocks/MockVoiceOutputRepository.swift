import Foundation
@testable import RafRaf

/// Test icin mock voice output repository.
final class MockVoiceOutputRepository: VoiceOutputRepositoryProtocol, @unchecked Sendable {
    var synthesizeResult: Result<TTSAudioResult, Error> = .success(
        VoiceOutputTestFactory.createAudioResult()
    )
    var synthesizeCallCount = 0
    var lastRequest: TTSRequest?

    var cachedAudio: TTSAudioResult?
    var getCachedCallCount = 0

    var clearCacheCallCount = 0

    func synthesizeSpeech(request: TTSRequest) async throws -> TTSAudioResult {
        synthesizeCallCount += 1
        lastRequest = request

        switch synthesizeResult {
        case .success(let result):
            return result
        case .failure(let error):
            throw error
        }
    }

    func getCachedAudio(for text: String) async -> TTSAudioResult? {
        getCachedCallCount += 1
        return cachedAudio
    }

    func clearCache() async {
        clearCacheCallCount += 1
    }
}
