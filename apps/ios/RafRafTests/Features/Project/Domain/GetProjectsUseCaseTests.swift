import Testing
@testable import RafRaf

/// GetProjectsUseCase testleri.
struct GetProjectsUseCaseTests {
    @Test("Basarili cagri repository'yi dogru parametrelerle cagirir")
    func executeCallsRepositoryWithCorrectParams() async throws {
        let mockRepo = MockProjectRepository()
        let expectedResult = ProjectListResult(
            projects: [Project(name: "Test")],
            total: 1,
            page: 1,
            pageSize: 20
        )
        mockRepo.getProjectsResult = .success(expectedResult)

        let useCase = GetProjectsUseCase(repository: mockRepo)
        let result = try await useCase.execute(status: .active, page: 2, pageSize: 10)

        #expect(mockRepo.getProjectsCallCount == 1)
        #expect(mockRepo.getProjectsLastStatus == .active)
        #expect(mockRepo.getProjectsLastPage == 2)
        #expect(mockRepo.getProjectsLastPageSize == 10)
        #expect(result.projects.count == 1)
    }

    @Test("Varsayilan parametreler dogru uygulanir")
    func executeUsesDefaultParameters() async throws {
        let mockRepo = MockProjectRepository()
        let useCase = GetProjectsUseCase(repository: mockRepo)

        _ = try await useCase.execute()

        #expect(mockRepo.getProjectsLastStatus == nil)
        #expect(mockRepo.getProjectsLastPage == 1)
        #expect(mockRepo.getProjectsLastPageSize == 20)
    }

    @Test("Repository hatasi yayilir")
    func executePropagatesError() async {
        let mockRepo = MockProjectRepository()
        mockRepo.getProjectsResult = .failure(NetworkError.invalidURL)

        let useCase = GetProjectsUseCase(repository: mockRepo)

        do {
            _ = try await useCase.execute()
            Issue.record("Hata bekleniyor ama basarili oldu")
        } catch {
            // Beklenen davranis
        }
    }
}

/// GetProjectDetailUseCase testleri.
struct GetProjectDetailUseCaseTests {
    @Test("Basarili cagri proje detayini dondurur")
    func executeReturnsProjectDetail() async throws {
        let mockRepo = MockProjectRepository()
        let expectedProject = Project(id: "test-id", name: "Detail Project")
        mockRepo.getProjectResult = .success(expectedProject)

        let useCase = GetProjectDetailUseCase(repository: mockRepo)
        let result = try await useCase.execute(projectId: "test-id")

        #expect(mockRepo.getProjectCallCount == 1)
        #expect(mockRepo.getProjectLastId == "test-id")
        #expect(result.name == "Detail Project")
    }

    @Test("Repository hatasi yayilir")
    func executeWithErrorPropagates() async {
        let mockRepo = MockProjectRepository()
        mockRepo.getProjectResult = .failure(NetworkError.httpError(statusCode: 404))

        let useCase = GetProjectDetailUseCase(repository: mockRepo)

        do {
            _ = try await useCase.execute(projectId: "nonexistent")
            Issue.record("Hata bekleniyor ama basarili oldu")
        } catch {
            // Beklenen davranis
        }
    }
}
