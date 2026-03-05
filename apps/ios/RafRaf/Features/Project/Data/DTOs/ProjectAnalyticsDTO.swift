import Foundation

/// Backend analitik endpoint yaniti DTO.
struct ProjectAnalyticsDTO: Codable, Sendable {
    let periodDays: Int
    let since: String
    let messages: MessagesStatsDTO
    let tokens: TokenStatsDTO
    let cost: CostStatsDTO
    let models: [String: Int]
    let dailyActivity: [DailyActivityDTO]

    struct MessagesStatsDTO: Codable, Sendable {
        let user: Int
        let assistant: Int
        let total: Int
    }

    struct TokenStatsDTO: Codable, Sendable {
        let total: Int
        let avgPerResponse: Int
    }

    struct CostStatsDTO: Codable, Sendable {
        let totalUsd: Double
        let events: Int
        let avgPerMessageUsd: Double
    }

    struct DailyActivityDTO: Codable, Sendable {
        let date: String
        let count: Int
    }
}
