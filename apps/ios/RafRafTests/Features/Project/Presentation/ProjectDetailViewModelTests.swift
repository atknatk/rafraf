import Testing
@testable import RafRaf

/// ProjectDetailViewModel testleri.
@MainActor
struct ProjectDetailViewModelTests {
    @Test("Proje detayi basariyla yuklenir")
    func loadProjectSuccess() async {
        let mockRepo = MockProjectRepository()
        let expectedProject = Project(
            id: "test-id",
            name: "Detail Project",
            description: "Test description",
            status: .active,
            techStack: ["Swift"]
        )
        mockRepo.getProjectResult = .success(expectedProject)

        let viewModel = ProjectDetailViewModel(
            getProjectDetailUseCase: GetProjectDetailUseCase(repository: mockRepo),
            projectId: "test-id"
        )

        await viewModel.loadProject()

        #expect(viewModel.project != nil)
        #expect(viewModel.project?.name == "Detail Project")
        #expect(viewModel.isLoading == false)
        #expect(viewModel.errorMessage == nil)
    }

    @Test("Proje detay yukleme hatasi error mesaji gosterir")
    func loadProjectError() async {
        let mockRepo = MockProjectRepository()
        mockRepo.getProjectResult = .failure(NetworkError.httpError(statusCode: 404))

        let viewModel = ProjectDetailViewModel(
            getProjectDetailUseCase: GetProjectDetailUseCase(repository: mockRepo),
            projectId: "nonexistent"
        )

        await viewModel.loadProject()

        #expect(viewModel.project == nil)
        #expect(viewModel.isLoading == false)
        #expect(viewModel.errorMessage != nil)
    }

    @Test("Hata mesaji dismiss edilir")
    func dismissErrorClearsMessage() async {
        let mockRepo = MockProjectRepository()
        mockRepo.getProjectResult = .failure(NetworkError.invalidURL)

        let viewModel = ProjectDetailViewModel(
            getProjectDetailUseCase: GetProjectDetailUseCase(repository: mockRepo),
            projectId: "test"
        )

        await viewModel.loadProject()
        #expect(viewModel.errorMessage != nil)

        viewModel.dismissError()
        #expect(viewModel.errorMessage == nil)
    }

    @Test("Yukleme durumunda tekrar yukleme yapmaz")
    func doesNotReloadWhileLoading() async {
        let mockRepo = MockProjectRepository()

        let viewModel = ProjectDetailViewModel(
            getProjectDetailUseCase: GetProjectDetailUseCase(repository: mockRepo),
            projectId: "test"
        )

        // İlk cagri
        await viewModel.loadProject()

        #expect(mockRepo.getProjectCallCount == 1)
    }
}
