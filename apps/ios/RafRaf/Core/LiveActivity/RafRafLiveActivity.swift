import ActivityKit
import Foundation
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

// MARK: - LiveActivityManaging Protocol

/// LiveActivityManager'in testable olmasi icin protocol.
/// Gercek ActivityKit dependency'si olmadan logic test edilebilir.
protocol LiveActivityManaging: Sendable {
    var hasActiveActivity: Bool { get }
    func startTask(taskId: String, taskTitle: String, projectName: String) async
    func updateTask(
        taskId: String,
        status: String,
        currentStep: String,
        progress: Double,
        completedSteps: Int,
        totalSteps: Int,
        phaseIcon: String,
        estimatedSeconds: Int?
    ) async
    func endTask(taskId: String) async
    /// Tum aktif task activity'lerini sonlandir.
    func endAllTasks() async
}

// MARK: - Live Activity Manager

/// Live Activity baslat/guncelle/durdur yoneticisi.
/// Birden fazla task icin es zamanli Live Activity destekler (Apple max 5).
@MainActor
final class LiveActivityManager: ObservableObject, LiveActivityManaging {
    static let shared = LiveActivityManager()

    private var currentActivity: Activity<RafRafActivityAttributes>?
    /// Aktif task activity'leri: taskId → activityId mapping
    private var activeTaskActivities: [String: String] = [:]
    /// Push token'i backend'e gondermek icin disaridan set edilen closure.
    /// Parametre: (taskId, pushToken) -> Void
    var pushTokenSender: (@Sendable (String, String) async -> Void)?
    private let logger = Logger(subsystem: "com.rafraf", category: "LiveActivity")

    nonisolated var hasActiveActivity: Bool {
        // ActivityKit activities are thread-safe to query
        !Activity<TaskActivityAttributes>.activities.isEmpty
    }

    private init() {}

    // MARK: - Legacy API (backward compat)

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
                pushType: .token
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

    // MARK: - Task-based API (Sprint 4)

    /// Yeni bir task Live Activity baslat (Dynamic Island + Lock Screen).
    /// Ayni taskId icin zaten activity varsa yeniden baslatmaz.
    /// Apple max 5 concurrent Live Activity destekler.
    func startTask(taskId: String, taskTitle: String, projectName: String) async {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            logger.info("Live activities not enabled on this device")
            return
        }

        // Bu task icin zaten activity varsa tekrar baslatma
        if activeTaskActivities[taskId] != nil {
            logger.debug("Task activity already exists for \(taskId), skipping start")
            return
        }

        let attributes = TaskActivityAttributes(
            taskId: taskId,
            taskTitle: taskTitle,
            projectName: projectName
        )

        let initialState = TaskActivityAttributes.ContentState(
            status: "started",
            currentStep: String(localized: "liveactivity.task.initializing"),
            progress: 0.0,
            completedSteps: 0,
            totalSteps: 1,
            estimatedSecondsRemaining: nil,
            phaseIcon: "circle"
        )

        do {
            // pushType: .token for local-only start (push updates added later)
            let activity = try Activity<TaskActivityAttributes>.request(
                attributes: attributes,
                content: .init(state: initialState, staleDate: nil),
                pushType: .token
            )
            activeTaskActivities[taskId] = activity.id
            logger.info("Task live activity started: \(activity.id) for task \(taskId)")

            // Push token guncellenmelerini gozlemle
            observePushTokenUpdates(for: activity.id, taskId: taskId)
        } catch {
            logger.error("Failed to start task live activity: \(error.localizedDescription)")
        }
    }

    /// Task Live Activity'yi guncelle. taskId ile hangi activity oldugu belirlenir.
    func updateTask(
        taskId: String,
        status: String,
        currentStep: String,
        progress: Double,
        completedSteps: Int,
        totalSteps: Int,
        phaseIcon: String,
        estimatedSeconds: Int?
    ) async {
        guard let activityId = activeTaskActivities[taskId] else {
            logger.warning("No active task activity for taskId \(taskId)")
            return
        }

        let newState = TaskActivityAttributes.ContentState(
            status: status,
            currentStep: currentStep,
            progress: progress,
            completedSteps: completedSteps,
            totalSteps: totalSteps,
            estimatedSecondsRemaining: estimatedSeconds,
            phaseIcon: phaseIcon
        )

        await Self.updateTaskActivity(activityId: activityId, state: newState)
        logger.debug("Task activity updated: taskId=\(taskId), status=\(status), progress=\(progress)")
    }

    /// Belirli bir task'in Live Activity'sini sonlandir.
    func endTask(taskId: String) async {
        guard let activityId = activeTaskActivities[taskId] else { return }

        let finalState = TaskActivityAttributes.ContentState(
            status: "completed",
            currentStep: String(localized: "liveactivity.task.completed"),
            progress: 1.0,
            completedSteps: 1,
            totalSteps: 1,
            estimatedSecondsRemaining: 0,
            phaseIcon: "checkmark.seal.fill"
        )

        await Self.endTaskActivity(activityId: activityId, finalState: finalState)
        activeTaskActivities.removeValue(forKey: taskId)
        logger.info("Task live activity ended for taskId \(taskId)")
    }

    /// Tum aktif task activity'lerini sonlandir.
    func endAllTasks() async {
        for taskId in activeTaskActivities.keys {
            await endTask(taskId: taskId)
        }
    }

    // MARK: - Nonisolated ActivityKit Helpers

    /// Activity'yi nonisolated context'te guncelle (Swift 6 sendability uyumlu).
    private nonisolated static func updateTaskActivity(
        activityId: String,
        state: TaskActivityAttributes.ContentState
    ) async {
        guard let activity = Activity<TaskActivityAttributes>.activities.first(where: { $0.id == activityId }) else {
            return
        }
        await activity.update(ActivityContent(state: state, staleDate: nil))
    }

    /// Activity'yi nonisolated context'te sonlandir (Swift 6 sendability uyumlu).
    private nonisolated static func endTaskActivity(
        activityId: String,
        finalState: TaskActivityAttributes.ContentState
    ) async {
        guard let activity = Activity<TaskActivityAttributes>.activities.first(where: { $0.id == activityId }) else {
            return
        }
        await activity.end(
            ActivityContent(state: finalState, staleDate: nil),
            dismissalPolicy: .after(Date().addingTimeInterval(5))
        )
    }

    // MARK: - Push Token Observation

    /// Push token guncellenmelerini async sequence ile gozlemle.
    private func observePushTokenUpdates(for activityId: String, taskId: String) {
        Task.detached { [weak self] in
            guard let activity = Activity<TaskActivityAttributes>.activities.first(where: { $0.id == activityId }) else {
                return
            }
            for await tokenData in activity.pushTokenUpdates {
                let tokenString = tokenData.map { String(format: "%02x", $0) }.joined()
                await self?.sendPushTokenToBackend(token: tokenString, taskId: taskId)
            }
        }
    }

    /// Push token'i backend'e gonderir.
    private func sendPushTokenToBackend(token: String, taskId: String) async {
        logger.info("Sending push token to backend for task \(taskId)")

        if let sender = pushTokenSender {
            await sender(taskId, token)
        } else {
            logger.warning("pushTokenSender not configured — push token not sent")
        }
    }
}
