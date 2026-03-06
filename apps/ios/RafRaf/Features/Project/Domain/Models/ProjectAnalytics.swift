import Foundation

/// Proje analitik domain modeli.
struct ProjectAnalytics: Sendable {
    let periodDays: Int
    let since: Date
    let userMessages: Int
    let assistantMessages: Int
    let totalTokens: Int
    let avgTokensPerResponse: Int
    let totalCostUSD: Double
    let avgCostPerMessageUSD: Double
    let modelDistribution: [String: Int]
    let dailyActivity: [DailyActivity]
}

/// Gunluk aktivite verisi.
struct DailyActivity: Identifiable, Sendable {
    let id: String
    let date: Date
    let messageCount: Int

    init(dateString: String, count: Int) {
        self.id = dateString
        self.date = {
            let fmt = DateFormatter()
            fmt.dateFormat = "yyyy-MM-dd"
            return fmt.date(from: dateString) ?? Date()
        }()
        self.messageCount = count
    }
}
