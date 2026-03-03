import Foundation

/// Auth DTO -> Domain model donusum katmani.
enum AuthMapper {
    /// TokenResponseDTO'yu AuthToken domain modeline donusturur.
    /// - Parameter dto: Backend'den gelen token yaniti.
    /// - Returns: AuthToken domain modeli.
    static func toDomain(_ dto: TokenResponseDTO) -> AuthToken {
        AuthToken(
            accessToken: dto.accessToken,
            refreshToken: dto.refreshToken,
            tokenType: dto.tokenType,
            expiresIn: dto.expiresIn,
            expiresAt: Date().addingTimeInterval(TimeInterval(dto.expiresIn))
        )
    }
}
