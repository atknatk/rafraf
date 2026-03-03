import Foundation

/// Login is mantigi.
/// Repository uzerinden backend'e login istegi gonderir.
struct LoginUseCase: Sendable {
    private let repository: AuthRepositoryProtocol

    init(repository: AuthRepositoryProtocol) {
        self.repository = repository
    }

    /// Login islemini gerceklestirir.
    /// - Parameters:
    ///   - email: Kullanici e-posta adresi.
    ///   - password: Kullanici sifresi.
    /// - Returns: JWT token bilgileri.
    func execute(email: String, password: String) async throws -> AuthToken {
        try await repository.login(email: email, password: password)
    }
}
