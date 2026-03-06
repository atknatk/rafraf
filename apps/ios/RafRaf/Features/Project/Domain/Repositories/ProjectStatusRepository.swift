import Foundation

/// Proje repository protokolu.
/// Domain katmani Data katmanindan izole kalir; bu protokol uzerinden iletisir.
protocol ProjectStatusRepositoryProtocol: Sendable {
    /// Proje listesini getirir.
    /// - Parameters:
    ///   - status: Opsiyonel durum filtresi
    ///   - page: Sayfa numarasi (1-indexed)
    ///   - pageSize: Sayfa basina proje sayisi
    /// - Returns: Proje listesi sonucu
    func getProjects(
        status: ProjectStatus?,
        agentId: String?,
        page: Int,
        pageSize: Int
    ) async throws -> ProjectListResult

    /// Proje detayini getirir.
    /// - Parameter projectId: Proje ID
    /// - Returns: Proje detay bilgisi
    func getProject(id projectId: String) async throws -> Project

    /// Proje durumunu gunceller.
    /// - Parameters:
    ///   - projectId: Proje ID
    ///   - status: Yeni durum
    /// - Returns: Guncellenmis proje
    func updateProjectStatus(projectId: String, status: ProjectStatus) async throws -> Project

    /// Duplicate projeleri temizler, silinen sayisini dondurur.
    func deduplicateProjects() async throws -> Int

    /// Yeni proje olusturur.
    func createProject(
        name: String,
        description: String?,
        repositoryURL: String?,
        localPath: String?,
        techStack: [String]
    ) async throws -> String

    /// Mevcut projeyi gunceller.
    func updateProject(
        projectId: String,
        name: String?,
        description: String?,
        repositoryURL: String?,
        localPath: String?,
        techStack: [String]?
    ) async throws -> Project
}

/// Proje listesi sonuc modeli.
struct ProjectListResult: Sendable, Equatable {
    let projects: [Project]
    let total: Int
    let page: Int
    let pageSize: Int

    var hasMore: Bool {
        page * pageSize < total
    }
}
