import ActivityKit
import os
import SwiftUI

/// RafRaf Live Activity attributes.
/// Dynamic Island ve Lock Screen'de AI aktivitesini gosterir.
struct RafRafActivityAttributes: ActivityAttributes {
    /// Degisen veriler (activity calisirken guncellenir).
    public struct ContentState: Codable, Hashable {
        /// Mevcut arac adi: "Dosya okunuyor", "Komut calistiriliyor" vb.
        var currentTool: String
        /// Ilerleme yuzdesi (0-100)
        var percentage: Int
        /// Faz aciklamasi
        var phaseLabel: String
        /// Aktif mi?
        var isActive: Bool
    }

    /// Proje adi (degismez)
    var projectName: String
}

// MARK: - Live Activity Manager

/// Live Activity baslat/guncelle/durdur yoneticisi.
@MainActor
final class LiveActivityManager: ObservableObject {
    static let shared = LiveActivityManager()

    private var currentActivity: Activity<RafRafActivityAttributes>?
    private let logger = Logger(subsystem: "com.rafraf", category: "LiveActivity")

    private init() {}

    /// Yeni bir Live Activity baslat.
    func start(projectName: String) {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            logger.info("Live activities not enabled on this device")
            return
        }

        // Zaten calisan activity varsa durdur
        stopCurrent()

        let attributes = RafRafActivityAttributes(projectName: projectName)
        let initialState = RafRafActivityAttributes.ContentState(
            currentTool: String(localized: "liveactivity.starting"),
            percentage: 0,
            phaseLabel: String(localized: "liveactivity.phase.starting"),
            isActive: true
        )

        do {
            let activity = try Activity<RafRafActivityAttributes>.request(
                attributes: attributes,
                content: .init(state: initialState, staleDate: nil),
                pushType: nil
            )
            currentActivity = activity
            logger.info("Live activity started: \(activity.id)")
        } catch {
            logger.error("Failed to start live activity: \(error.localizedDescription)")
        }
    }

    /// Live Activity'yi guncelle.
    func update(tool: String, percentage: Int, phaseLabel: String) {
        guard let activity = currentActivity else { return }

        let newState = RafRafActivityAttributes.ContentState(
            currentTool: tool,
            percentage: percentage,
            phaseLabel: phaseLabel,
            isActive: true
        )

        Task {
            await activity.update(using: newState)
        }
    }

    /// Live Activity'yi bitir.
    func end() {
        guard let activity = currentActivity else { return }

        let finalState = RafRafActivityAttributes.ContentState(
            currentTool: String(localized: "liveactivity.completed"),
            percentage: 100,
            phaseLabel: String(localized: "liveactivity.phase.completed"),
            isActive: false
        )

        Task {
            await activity.end(using: finalState, dismissalPolicy: .after(Date().addingTimeInterval(5)))
            logger.info("Live activity ended")
        }
        currentActivity = nil
    }

    private func stopCurrent() {
        guard let activity = currentActivity else { return }
        Task {
            await activity.end(dismissalPolicy: .immediate)
        }
        currentActivity = nil
    }
}
