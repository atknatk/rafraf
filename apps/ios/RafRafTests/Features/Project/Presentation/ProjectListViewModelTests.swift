import Testing
@testable import RafRaf

/// ProjectListViewModel testleri.
@MainActor
struct ProjectListViewModelTests {
    @Test("Proje listesi basariyla yuklenir")
    func loadProjectsSuccess() async {
        let mockRepo = MockProjectRepository()
        let projects = [
            Project(name: "Project 1", status: .active),
            Project(name: "Project 2", status: .pending)
        ]
        mockRepo.getProjectsResult = .success(
            ProjectListResult(projects: projects, total: 2, page: 1, pageSize: 20)
        )

        let viewModel = ProjectListViewModel(
            getProjectsUseCase: GetProjectsUseCase(repository: mockRepo)
        )

        await viewModel.loadProjects()

        #expect(viewModel.projects.count == 2)
        #expect(viewModel.isLoading == false)
        #expect(viewModel.errorMessage == nil)
        #expect(viewModel.hasMorePages == false)
    }

    @Test("Proje listesi yukleme hatasi error mesaji gosterir")
    func loadProjectsError() async {
        let mockRepo = MockProjectRepository()
        mockRepo.getProjectsResult = .failure(NetworkError.invalidURL)

        let viewModel = ProjectListViewModel(
            getProjectsUseCase: GetProjectsUseCase(repository: mockRepo)
        )

        await viewModel.loadProjects()

        #expect(viewModel.projects.isEmpty)
        #expect(viewModel.isLoading == false)
        #expect(viewModel.errorMessage != nil)
    }

    @Test("Pull-to-refresh projeleri yeniler")
    func refreshProjectsReloadsData() async {
        let mockRepo = MockProjectRepository()
        let projects = [Project(name: "Refreshed")]
        mockRepo.getProjectsResult = .success(
            ProjectListResult(projects: projects, total: 1, page: 1, pageSize: 20)
        )

        let viewModel = ProjectListViewModel(
            getProjectsUseCase: GetProjectsUseCase(repository: mockRepo)
        )

        await viewModel.refreshProjects()

        #expect(viewModel.projects.count == 1)
        #expect(viewModel.isRefreshing == false)
    }

    @Test("Durum filtresi dogru uygulanir")
    func filterByStatusCallsRepositoryWithFilter() async {
        let mockRepo = MockProjectRepository()
        mockRepo.getProjectsResult = .success(
            ProjectListResult(projects: [], total: 0, page: 1, pageSize: 20)
        )

        let viewModel = ProjectListViewModel(
            getProjectsUseCase: GetProjectsUseCase(repository: mockRepo)
        )

        await viewModel.filterByStatus(.pending)

        #expect(viewModel.selectedFilter == .pending)
        #expect(mockRepo.getProjectsLastStatus == .pending)
    }

    @Test("Daha fazla proje yukleme sayfalama yapar")
    func loadMoreProjectsAppends() async {
        let mockRepo = MockProjectRepository()
        let initialProjects = [Project(name: "First")]
        mockRepo.getProjectsResult = .success(
            ProjectListResult(projects: initialProjects, total: 30, page: 1, pageSize: 20)
        )

        let viewModel = ProjectListViewModel(
            getProjectsUseCase: GetProjectsUseCase(repository: mockRepo)
        )

        await viewModel.loadProjects()
        #expect(viewModel.hasMorePages == true)

        let moreProjects = [Project(name: "Second")]
        mockRepo.getProjectsResult = .success(
            ProjectListResult(projects: moreProjects, total: 30, page: 2, pageSize: 20)
        )

        await viewModel.loadMoreProjects()

        #expect(viewModel.projects.count == 2)
    }

    @Test("Hata mesaji dismiss edilir")
    func dismissErrorClearsMessage() async {
        let mockRepo = MockProjectRepository()
        mockRepo.getProjectsResult = .failure(NetworkError.invalidURL)

        let viewModel = ProjectListViewModel(
            getProjectsUseCase: GetProjectsUseCase(repository: mockRepo)
        )

        await viewModel.loadProjects()
        #expect(viewModel.errorMessage != nil)

        viewModel.dismissError()
        #expect(viewModel.errorMessage == nil)
    }
}
