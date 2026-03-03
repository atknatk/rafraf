import Foundation

/// ScreenshotDTO -> Screenshot domain modeli donusturucusu.
enum ScreenshotMapper {
    /// ISO8601 tarih formatlayicisi.
    private static let dateFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    /// DTO'yu domain modeline donusturur.
    /// - Parameter dto: API'den gelen ScreenshotDTO.
    /// - Returns: Screenshot domain modeli.
    static func toDomain(_ dto: ScreenshotDTO) -> Screenshot {
        let timestamp = dateFormatter.date(from: dto.timestamp) ?? Date()

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
