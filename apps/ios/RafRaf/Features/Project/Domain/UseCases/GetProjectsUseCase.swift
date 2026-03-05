import Foundation

/// Proje listesi use case.
/// Projeleri filtre ve sayfalama ile getirir.
final class GetProjectsUseCase: Sendable {
    private let repository: ProjectStatusRepositoryProtocol

    init(repository: ProjectStatusRepositoryProtocol) {
        self.repository = repository
    }

    /// Proje listesini getirir.
    /// - Parameters:
    ///   - status: Opsiyonel durum filtresi
    ///   - page: Sayfa numarasi
    ///   - pageSize: Sayfa basina proje sayisi
    /// - Returns: Proje listesi sonucu
    func execute(
        status: ProjectStatus? = nil,
        agentId: String? = nil,
        page: Int = 1,
        pageSize: Int = 20
    ) async throws -> ProjectListResult {
        try await repository.getProjects(
            status: status,
            agentId: agentId,
            page: page,
            pageSize: pageSize
        )
    }
}
