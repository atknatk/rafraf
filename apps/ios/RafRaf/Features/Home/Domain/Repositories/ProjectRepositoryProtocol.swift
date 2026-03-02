import Foundation

/// Proje repository protokolu.
/// Domain katmani Data katmanindan izole kalir; bu protokol uzerinden iletisir.
protocol ProjectRepositoryProtocol: Sendable {
    /// Tum projeleri getirir.
    func fetchProjects() async throws -> [Project]

    /// Belirtilen ID'li projeyi getirir.
    func fetchProject(by id: String) async throws -> Project
}
