import Foundation

/// Screenshot API response DTO.
struct ScreenshotDTO: Codable, Sendable {
    let id: String
    let url: String
    let title: String?
    let timestamp: String
    let width: Int?
    let height: Int?
}
