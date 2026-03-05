import Foundation

/// Proje durumunu gunceller (aktif/arsiv vb.).
final class UpdateProjectStatusUseCase: Sendable {
    private let repository: ProjectStatusRepositoryProtocol

    init(repository: ProjectStatusRepositoryProtocol) {
        self.repository = repository
    }

    /// Proje durumunu gunceller.
    /// - Parameters:
    ///   - projectId: Proje ID
    ///   - status: Yeni durum
    /// - Returns: Guncellenmis proje
    func execute(projectId: String, status: ProjectStatus) async throws -> Project {
        try await repository.updateProjectStatus(projectId: projectId, status: status)
    }
}
