import Foundation

/// Kullanici profilini API'den yukler.
struct LoadProfileUseCase: Sendable {
    private let repository: UserRepositoryProtocol

    init(repository: UserRepositoryProtocol) {
        self.repository = repository
    }

    func execute() async throws -> UserProfile {
        try await repository.fetchCurrentUser()
    }
}
