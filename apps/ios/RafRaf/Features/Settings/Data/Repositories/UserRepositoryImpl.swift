import Foundation

/// Kullanici profil API repository implementasyonu.
final class UserRepositoryImpl: UserRepositoryProtocol, @unchecked Sendable {
    private let networkClient: NetworkClient

    init(networkClient: NetworkClient) {
        self.networkClient = networkClient
    }

    func fetchCurrentUser() async throws -> UserProfile {
        let dto: UserProfileDTO = try await networkClient.get(path: "/auth/profile")
        return UserProfileMapper.toDomain(dto)
    }

    func logout() async throws {
        // Logout sadece local token silme ile yapilir (AuthManager tarafindan)
    }

    func updateDisplayName(_ displayName: String) async throws -> UserProfile {
        let body = ProfileUpdateDTO(displayName: displayName)
        let dto: UserProfileDTO = try await networkClient.patch(path: "/auth/profile", body: body)
        return UserProfileMapper.toDomain(dto)
    }
}

/// Profil guncelleme request DTO.
private struct ProfileUpdateDTO: Codable, Sendable {
    let displayName: String
}
