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
        page: Int,
        pageSize: Int
    ) async throws -> ProjectListResult

    /// Proje detayini getirir.
    /// - Parameter projectId: Proje ID
    /// - Returns: Proje detay bilgisi
    func getProject(id projectId: String) async throws -> Project
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
