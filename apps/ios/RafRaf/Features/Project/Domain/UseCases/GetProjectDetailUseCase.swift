import Foundation

/// Proje detay use case.
/// Tek projenin detay bilgisini getirir.
final class GetProjectDetailUseCase: Sendable {
    private let repository: ProjectRepositoryProtocol

    init(repository: ProjectRepositoryProtocol) {
        self.repository = repository
    }

    /// Proje detayini getirir.
    /// - Parameter projectId: Proje ID
    /// - Returns: Proje domain modeli
    func execute(projectId: String) async throws -> Project {
        try await repository.getProject(id: projectId)
    }
}
