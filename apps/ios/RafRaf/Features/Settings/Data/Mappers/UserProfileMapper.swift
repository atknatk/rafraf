import Foundation

/// Kullanici profil DTO -> Domain donusturucu.
enum UserProfileMapper {
    /// DTO'yu domain modeline donusturur.
    static func toDomain(_ dto: UserProfileDTO) -> UserProfile {
        let dateFormatter = ISO8601DateFormatter()

        return UserProfile(
            id: dto.id,
            displayName: dto.displayName,
            email: dto.email,
            avatarURL: dto.avatarUrl.flatMap { URL(string: $0) },
            createdAt: dateFormatter.date(from: dto.createdAt) ?? Date()
        )
    }
}
