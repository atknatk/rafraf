import Foundation

/// Subscription kullanim API response DTO.
/// Backend `GET /api/v1/subscription/usage` kontratina uygun.
struct SubscriptionUsageDTO: Codable, Sendable {
    let subscriptionType: String
    let email: String?
    let orgName: String?
    let todayUsage: DailyUsageStatsDTO
    let recentDays: [DailyUsageStatsDTO]
    let totalMessagesToday: Int
    let isRateLimited: Bool
    let rateLimitResetAt: String?
    let usagePercent: Double
    let dailyMessageLimit: Int
    let warningThresholdReached: Bool
    let limitExceeded: Bool
    let lastFetchedAt: String
}

/// Gunluk kullanim istatistikleri DTO.
struct DailyUsageStatsDTO: Codable, Sendable {
    let date: String
    let messageCount: Int
    let sessionCount: Int
    let toolCallCount: Int
}
