import Foundation

/// Login istegi DTO.
/// Backend `POST /api/v1/auth/token` endpoint'ine gonderilir.
struct TokenRequestDTO: Codable, Sendable {
    let email: String
    let password: String
}

/// Token yenileme istegi DTO.
/// Backend `POST /api/v1/auth/refresh` endpoint'ine gonderilir.
struct RefreshRequestDTO: Codable, Sendable {
    let refreshToken: String
}

/// Token yaniti DTO.
/// Backend auth endpoint'lerinden donen yanit.
struct TokenResponseDTO: Codable, Sendable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let expiresIn: Int
}
