import Foundation

/// Kullanici profil API response DTO.
struct UserProfileDTO: Codable, Sendable {
    let id: String
    let displayName: String
    let email: String
    let avatarUrl: String?
    let createdAt: String
}
