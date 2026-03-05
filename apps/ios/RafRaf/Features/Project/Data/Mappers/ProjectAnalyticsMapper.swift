import Foundation

enum ProjectAnalyticsMapper {
    static func toDomain(from dto: ProjectAnalyticsDTO) -> ProjectAnalytics {
        let since = ISO8601DateFormatter().date(from: dto.since) ?? Date()
        let daily = dto.dailyActivity.map {
            DailyActivity(dateString: $0.date, count: $0.count)
        }
        return ProjectAnalytics(
            periodDays: dto.periodDays,
            since: since,
            userMessages: dto.messages.user,
            assistantMessages: dto.messages.assistant,
            totalTokens: dto.tokens.total,
            avgTokensPerResponse: dto.tokens.avgPerResponse,
            totalCostUSD: dto.cost.totalUsd,
            avgCostPerMessageUSD: dto.cost.avgPerMessageUsd,
            modelDistribution: dto.models,
            dailyActivity: daily
        )
    }
}
