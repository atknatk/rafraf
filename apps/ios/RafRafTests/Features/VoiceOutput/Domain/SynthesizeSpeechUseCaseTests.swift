import Foundation
import Testing
@testable import RafRaf

/// SynthesizeSpeechUseCase testleri.
@Suite("SynthesizeSpeechUseCase Tests")
struct SynthesizeSpeechUseCaseTests {

    // MARK: - Helpers

    private func makeSUT(
        repository: MockVoiceOutputRepository = MockVoiceOutputRepository()
    ) -> (SynthesizeSpeechUseCase, MockVoiceOutputRepository) {
        let useCase = SynthesizeSpeechUseCase(repository: repository)
        return (useCase, repository)
    }

    // MARK: - Success Cases

    @Test("Basarili sentez: repository cagirilmali")
    func successfulSynthesis() async throws {
        let (useCase, repo) = makeSUT()
        let request = VoiceOutputTestFactory.createRequest()

        let result = try await useCase.execute(request: request)

        #expect(repo.synthesizeCallCount == 1)
        #expect(result.text == request.text)
    }

    @Test("Cache hit: repository synthesize cagirilmamali")
    func cacheHit() async throws {
        let repo = MockVoiceOutputRepository()
        let cached = VoiceOutputTestFactory.createAudioResult(text: "Cached text")
        repo.cachedAudio = cached
        let (useCase, _) = makeSUT(repository: repo)
        let request = VoiceOutputTestFactory.createRequest(text: "Cached text")

        let result = try await useCase.execute(request: request)

        #expect(repo.getCachedCallCount == 1)
        #expect(repo.synthesizeCallCount == 0)
        #expect(result.text == "Cached text")
    }

    @Test("Cache miss: repository synthesize cagirilmali")
    func cacheMiss() async throws {
        let repo = MockVoiceOutputRepository()
        repo.cachedAudio = nil
        let (useCase, _) = makeSUT(repository: repo)
        let request = VoiceOutputTestFactory.createRequest()

        _ = try await useCase.execute(request: request)

        #expect(repo.getCachedCallCount == 1)
        #expect(repo.synthesizeCallCount == 1)
    }

    // MARK: - Error Cases

    @Test("Bos metin: emptyText hatasi firlatmali")
    func emptyText() async {
        let (useCase, _) = makeSUT()
        let request = VoiceOutputTestFactory.createRequest(text: "")

        do {
            _ = try await useCase.execute(request: request)
            #expect(Bool(false), "Hata firlatilmadi")
        } catch is VoiceOutputUseCaseError {
            // Beklenen hata
        } catch {
            #expect(Bool(false), "Yanlis hata tipi: \(error)")
        }
    }

    @Test("Sadece bosluk: emptyText hatasi firlatmali")
    func whitespaceOnlyText() async {
        let (useCase, _) = makeSUT()
        let request = VoiceOutputTestFactory.createRequest(text: "   \n\t  ")

        do {
            _ = try await useCase.execute(request: request)
            #expect(Bool(false), "Hata firlatilmadi")
        } catch is VoiceOutputUseCaseError {
            // Beklenen hata
        } catch {
            #expect(Bool(false), "Yanlis hata tipi: \(error)")
        }
    }

    @Test("API hatasi: repository hatasi iletilmeli")
    func apiError() async {
        let repo = MockVoiceOutputRepository()
        repo.synthesizeResult = .failure(VoiceOutputRepositoryError.ttsRequestFailed)
        let (useCase, _) = makeSUT(repository: repo)
        let request = VoiceOutputTestFactory.createRequest()

        do {
            _ = try await useCase.execute(request: request)
            #expect(Bool(false), "Hata firlatilmadi")
        } catch is VoiceOutputRepositoryError {
            // Beklenen hata
        } catch {
            #expect(Bool(false), "Yanlis hata tipi: \(error)")
        }
    }

    @Test("Request parametreleri repository'ye iletilmeli")
    func requestParametersPassed() async throws {
        let repo = MockVoiceOutputRepository()
        let (useCase, _) = makeSUT(repository: repo)
        let request = VoiceOutputTestFactory.createRequest(
            text: "Ozel metin",
            voice: .shimmer,
            speed: 1.5
        )

        _ = try await useCase.execute(request: request)

        #expect(repo.lastRequest?.text == "Ozel metin")
        #expect(repo.lastRequest?.voice == .shimmer)
        #expect(repo.lastRequest?.speed == 1.5)
    }
}
