import Foundation
import Testing
@testable import RafRaf

/// DownloadFileUseCase testleri.
@Suite("DownloadFileUseCase Tests")
struct DownloadFileUseCaseTests {

    // MARK: - Helpers

    private func makeSUT(
        repository: MockFileRepository = MockFileRepository()
    ) -> (DownloadFileUseCase, MockFileRepository) {
        let useCase = DownloadFileUseCase(repository: repository)
        return (useCase, repository)
    }

    // MARK: - Success

    @Test("Basarili dosya indirmeli")
    func executeSuccess() async throws {
        let expectedFile = FileTestFactory.createSharedFile(
            name: "rapor.pdf",
            localURL: URL(fileURLWithPath: "/tmp/rapor.pdf")
        )
        let repo = MockFileRepository()
        repo.downloadResult = .success(expectedFile)
        let (useCase, _) = makeSUT(repository: repo)

        let result = try await useCase.execute(
            projectId: "123",
            fileKey: "projects/123/rapor.pdf"
        )

        #expect(result.name == "rapor.pdf")
        #expect(result.localURL != nil)
        #expect(repo.downloadCallCount == 1)
        #expect(repo.lastDownloadProjectId == "123")
        #expect(repo.lastDownloadFileKey == "projects/123/rapor.pdf")
    }

    // MARK: - Error

    @Test("Repository hatasi durumunda hata firlatmali")
    func executeThrowsOnError() async {
        let repo = MockFileRepository()
        repo.downloadResult = .failure(FileRepositoryError.downloadFailed(statusCode: 404))
        let (useCase, _) = makeSUT(repository: repo)

        await #expect(throws: FileRepositoryError.self) {
            try await useCase.execute(
                projectId: "123",
                fileKey: "projects/123/missing.pdf"
            )
        }
    }
}
