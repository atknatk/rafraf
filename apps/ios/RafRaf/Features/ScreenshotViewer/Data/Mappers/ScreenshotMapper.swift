import Foundation

/// ScreenshotDTO -> Screenshot domain modeli donusturucusu.
enum ScreenshotMapper {
    /// DTO'yu domain modeline donusturur.
    /// - Parameter dto: API'den gelen ScreenshotDTO.
    /// - Returns: Screenshot domain modeli.
    static func toDomain(_ dto: ScreenshotDTO) -> Screenshot {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let timestamp = formatter.date(from: dto.timestamp) ?? Date()

        return Screenshot(
            id: dto.id,
            url: dto.url,
            title: dto.title,
            timestamp: timestamp,
            width: dto.width,
            height: dto.height
        )
    }
}
