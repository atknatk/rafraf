import Foundation
import Testing
@testable import RafRaf

/// LoadScreenshotUseCase testleri.
@Suite("LoadScreenshotUseCase Tests")
struct LoadScreenshotUseCaseTests {

    // MARK: - Helpers

    private func makeSUT(
        repository: MockScreenshotRepository = MockScreenshotRepository()
    ) -> (LoadScreenshotUseCase, MockScreenshotRepository) {
        let useCase = LoadScreenshotUseCase(repository: repository)
        return (useCase, repository)
    }

    // MARK: - Success

    @Test("Basarili screenshot yukleme")
    func executeSuccess() async throws {
        let expectedScreenshot = ScreenshotTestFactory.makeScreenshot(id: "sc-success")
        let repo = MockScreenshotRepository()
        repo.fetchScreenshotResult = .success(expectedScreenshot)
        let (useCase, _) = makeSUT(repository: repo)

        let result = try await useCase.execute(screenshotId: "sc-success")

        #expect(result.id == "sc-success")
        #expect(result.url == expectedScreenshot.url)
        #expect(repo.fetchScreenshotCallCount == 1)
        #expect(repo.lastScreenshotId == "sc-success")
    }

    // MARK: - Error

    @Test("Screenshot yukleme hatasi")
    func executeError() async {
        let repo = MockScreenshotRepository()
        repo.fetchScreenshotResult = .failure(ScreenshotRepositoryTestError.networkError)
        let (useCase, _) = makeSUT(repository: repo)

        do {
            _ = try await useCase.execute(screenshotId: "sc-error")
            Issue.record("Hata firlatilmasi bekleniyordu")
        } catch {
            #expect(repo.fetchScreenshotCallCount == 1)
        }
    }

    @Test("Screenshot bulunamadi hatasi")
    func executeNotFound() async {
        let repo = MockScreenshotRepository()
        repo.fetchScreenshotResult = .failure(ScreenshotRepositoryTestError.notFound)
        let (useCase, _) = makeSUT(repository: repo)

        do {
            _ = try await useCase.execute(screenshotId: "not-exists")
            Issue.record("Hata firlatilmasi bekleniyordu")
        } catch {
            #expect(repo.lastScreenshotId == "not-exists")
        }
    }

    @Test("Repository dogru parametrelerle cagirilmali")
    func executeCallsRepository() async throws {
        let (useCase, repo) = makeSUT()

        _ = try await useCase.execute(screenshotId: "param-test")

        #expect(repo.fetchScreenshotCallCount == 1)
        #expect(repo.lastScreenshotId == "param-test")
    }
}
