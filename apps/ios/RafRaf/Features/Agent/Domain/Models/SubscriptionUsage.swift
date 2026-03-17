import Foundation

/// Claude Max subscription kullanim bilgileri.
struct SubscriptionUsage: Sendable, Equatable {
    let subscriptionType: String
    let email: String?
    let orgName: String?
    let todayUsage: DailyUsageStats
    let recentDays: [DailyUsageStats]
    let totalMessagesToday: Int
    let isRateLimited: Bool
    let rateLimitResetAt: Date?
    let usagePercent: Double
    let dailyMessageLimit: Int
    let warningThresholdReached: Bool
    let limitExceeded: Bool
    let lastFetchedAt: Date
}

/// Gunluk kullanim istatistikleri.
struct DailyUsageStats: Sendable, Equatable, Identifiable {
    var id: String { date }
    let date: String
    let messageCount: Int
    let sessionCount: Int
    let toolCallCount: Int
}
