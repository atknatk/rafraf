import Foundation

/// JWT token bilgilerini temsil eden domain modeli.
struct AuthToken: Sendable, Equatable {
    /// JWT access token.
    let accessToken: String
    /// JWT refresh token.
    let refreshToken: String
    /// Token tipi (her zaman "bearer").
    let tokenType: String
    /// Access token gecerlilik suresi (saniye).
    let expiresIn: Int
    /// Token'in gecersiz olacagi zaman.
    let expiresAt: Date
}
