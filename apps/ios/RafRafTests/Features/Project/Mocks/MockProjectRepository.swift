import Foundation
@testable import RafRaf

/// Test icin mock proje repository.
final class MockProjectRepository: ProjectStatusRepositoryProtocol, @unchecked Sendable {
    // MARK: - Call Tracking

    var getProjectsCallCount = 0
    var getProjectsLastStatus: ProjectStatus?
    var getProjectsLastPage: Int?
    var getProjectsLastPageSize: Int?

    var getProjectCallCount = 0
    var getProjectLastId: String?

    // MARK: - Return Values

    var getProjectsResult: Result<ProjectListResult, Error> = .success(
        ProjectListResult(projects: [], total: 0, page: 1, pageSize: 20)
    )

    var getProjectResult: Result<Project, Error> = .success(
        Project(name: "Mock Project")
    )

    // MARK: - Protocol

    func getProjects(
        status: ProjectStatus?,
        page: Int,
        pageSize: Int
    ) async throws -> ProjectListResult {
        getProjectsCallCount += 1
        getProjectsLastStatus = status
        getProjectsLastPage = page
        getProjectsLastPageSize = pageSize
        return try getProjectsResult.get()
    }

    func getProject(id projectId: String) async throws -> Project {
        getProjectCallCount += 1
        getProjectLastId = projectId
        return try getProjectResult.get()
    }
}
