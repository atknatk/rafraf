import Foundation

/// Kullanici profil domain modeli.
struct UserProfile: Sendable, Equatable {
    let id: String
    let displayName: String
    let email: String
    let avatarURL: URL?
    let createdAt: Date
}
