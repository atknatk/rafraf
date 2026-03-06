import Foundation

/// Data shared between main app and widget extension via UserDefaults App Group.
/// App Group ID: group.com.atknatk.rafraf
struct WidgetData: Codable {
    let agentName: String
    let agentStatus: String  // "online" | "offline" | "busy"
    let todayMessageCount: Int
    let pulseSummary: String?
    let updatedAt: Date

    static let empty = WidgetData(
        agentName: "RafRaf",
        agentStatus: "offline",
        todayMessageCount: 0,
        pulseSummary: nil,
        updatedAt: Date()
    )
}

/// Writes widget data to shared UserDefaults so the widget extension can read it.
@MainActor final class WidgetDataService {
    static let shared = WidgetDataService()
    private let defaults = UserDefaults(suiteName: "group.com.atknatk.rafraf") ?? .standard
    private let key = "rafraf.widget.data"

    private init() {}

    func update(agentName: String, agentStatus: String, todayMessageCount: Int, pulseSummary: String?) {
        let data = WidgetData(
            agentName: agentName,
            agentStatus: agentStatus,
            todayMessageCount: todayMessageCount,
            pulseSummary: pulseSummary,
            updatedAt: Date()
        )
        if let encoded = try? JSONEncoder().encode(data) {
            defaults.set(encoded, forKey: key)
        }
        WidgetDataService.reloadTimelines()
    }

    func read() -> WidgetData {
        guard let raw = defaults.data(forKey: key),
              let data = try? JSONDecoder().decode(WidgetData.self, from: raw)
        else { return .empty }
        return data
    }

    /// Triggers widget timeline reload.
    /// Called from the widget extension context; no-op in main app target
    /// (WidgetCenter is available in extensions only — call from extension entry point).
    static func reloadTimelines() {
        // WidgetCenter.shared.reloadAllTimelines()
        // Uncomment in widget extension target where WidgetKit is linked.
    }
}
