import Foundation

/// Kullanici repository protokolu.
/// Domain katmani Data katmanindan izole kalir; bu protokol uzerinden iletisir.
protocol UserRepositoryProtocol: Sendable {
    /// Aktif kullanicinin profilini getirir.
    func fetchCurrentUser() async throws -> UserProfile

    /// Goruntu adini gunceller.
    func updateDisplayName(_ displayName: String) async throws -> UserProfile

    /// Cikis yapar.
    func logout() async throws
}
