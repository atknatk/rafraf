import Foundation

/// Kullanici profilini gunceller.
struct UpdateProfileUseCase: Sendable {
    private let repository: UserRepositoryProtocol

    init(repository: UserRepositoryProtocol) {
        self.repository = repository
    }

    func execute(displayName: String) async throws -> UserProfile {
        try await repository.updateDisplayName(displayName)
    }
}
