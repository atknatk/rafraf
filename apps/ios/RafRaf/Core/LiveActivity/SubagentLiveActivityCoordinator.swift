import Foundation
import os

/// Bridge subagent.spawned/progress/completed olaylarini Live Activity
/// guncellemelerine ceviren ince koordinator.
///
/// Doc 10 §8 — T3.1 Live Activity polish kabul kriteri:
/// "Live Activity update test (yeni subagent spawn'da)".
///
/// Davranis:
///   - Belirli bir session icin ilk subagent spawn olduğunda Activity baslar.
///   - Yeni subagent spawn'larinda var olan Activity guncellenir (count + son
///     status icon).
///   - Tum subagent'lar tamamlandığında 30s sonra Activity dismiss edilir
///     (autoDismissDelay parametresi ile test edilebilir).
///   - Birden fazla session destegi yoktur — coordinator session basina bir
///     kez baslatilir; gerek olursa cogaltilabilir. Doc 10 kapsamiyla uyumlu.
///
/// Coordinator pure logic'tir; ActivityKit'e dogrudan dokunmaz —
/// `LiveActivityManaging` protokolu uzerinden calisir, bu sayede test
/// edilebilir.
@MainActor
final class SubagentLiveActivityCoordinator {
    /// Activity hangi session icin acik (ilk spawn olan subagent'in
    /// `sessionId`'si). Coordinator yenisini reddeder ve aynisini guncellemeye
    /// devam eder.
    private(set) var trackedSessionId: String?

    /// Activity'nin Live Activity Manager'a kayitli `taskId`'si — coordinator
    /// kendi UUID'sini uretir cunku Live Activity birden fazla subagent'in
    /// toplamini gosteren tek bir kart olarak tasarlandi.
    private(set) var trackedActivityTaskId: String?

    /// Toplam aktif subagent sayisi (in_progress veya spawned). Live Activity
    /// uzerindeki count badge bu deger ile guncellenir.
    private(set) var lastActiveCount: Int = 0

    /// Son guncel status — Activity ikonu icin kullanilir.
    private(set) var lastDominantStatus: SubagentStatus?

    /// Tum subagent'lar tamamlandiginda Activity'yi otomatik dismiss etmek
    /// icin bekleme suresi.
    private let autoDismissDelay: Duration

    private let manager: LiveActivityManaging
    private let activityIdProvider: @Sendable () -> String
    private let logger = AppLogger.logger(for: "SubagentLiveActivity")

    /// Pending dismiss task'i — baska bir spawn gelirse iptal edilir.
    private var pendingDismissTask: Task<Void, Never>?

    init(
        manager: LiveActivityManaging,
        autoDismissDelay: Duration = .seconds(30),
        activityIdProvider: @escaping @Sendable () -> String = { UUID().uuidString }
    ) {
        self.manager = manager
        self.autoDismissDelay = autoDismissDelay
        self.activityIdProvider = activityIdProvider
    }

    /// Bridge tarafindan gelen guncel subagent listesini isle. UI tarafi her
    /// yeni snapshot'ta bu metoda cagirir.
    func ingest(snapshot: [Subagent]) async {
        // Bu coordinator tek bir session'a bagli — ilk spawn'in session'i
        // tracked kabul edilir. Snapshot bossa hiçbir sey yapma (initial state).
        guard !snapshot.isEmpty else {
            return
        }

        // Snapshot icindeki ilk subagent'in session'ini referans alalim.
        let primarySessionId = trackedSessionId ?? snapshot[0].sessionId
        let sessionScoped = snapshot.filter { $0.sessionId == primarySessionId }

        let activeCount = sessionScoped.filter {
            $0.status == .spawned || $0.status == .inProgress
        }.count
        let dominant = dominantStatus(in: sessionScoped)

        if trackedActivityTaskId == nil {
            // Henuz Activity baslatilmamis — ilk subagent gorulduginde baslat.
            await startActivity(
                sessionId: primarySessionId,
                count: max(activeCount, 1),
                status: dominant
            )
        } else {
            await updateActivity(
                count: activeCount,
                status: dominant,
                totalCount: sessionScoped.count
            )
        }

        lastActiveCount = activeCount
        lastDominantStatus = dominant

        // Hicbir aktif subagent kalmadiysa Activity'yi 30s sonra dismiss et.
        if activeCount == 0 {
            scheduleDismiss()
        } else {
            cancelPendingDismiss()
        }
    }

    /// Mevcut Activity'yi hemen sonlandir (View kapandiginda vb.)
    func dismissNow() async {
        cancelPendingDismiss()
        guard let activityTaskId = trackedActivityTaskId else { return }
        await manager.endTask(taskId: activityTaskId)
        resetTracking()
    }

    /// Birden fazla subagent statusunu tek bir "dominant" status'a indirger.
    /// Sirasi: failed > inProgress > spawned > completed.
    nonisolated static func resolveDominantStatus(in subagents: [Subagent]) -> SubagentStatus? {
        guard !subagents.isEmpty else { return nil }
        if subagents.contains(where: { $0.status == .failed }) {
            return .failed
        }
        if subagents.contains(where: { $0.status == .inProgress }) {
            return .inProgress
        }
        if subagents.contains(where: { $0.status == .spawned }) {
            return .spawned
        }
        return .completed
    }

    nonisolated static func phaseIcon(for status: SubagentStatus?) -> String {
        switch status {
        case .spawned, .inProgress: return "person.2.gobackward"
        case .completed: return "checkmark.seal.fill"
        case .failed: return "exclamationmark.triangle.fill"
        case .none: return "circle"
        }
    }

    nonisolated static func statusKey(for status: SubagentStatus?) -> String {
        switch status {
        case .spawned, .inProgress: return "in_progress"
        case .completed: return "completed"
        case .failed: return "failed"
        case .none: return "started"
        }
    }

    /// Test gorunurlugu icin internal helper.
    nonisolated static func progress(active: Int, completed: Int) -> Double {
        let total = active + completed
        guard total > 0 else { return 0 }
        return Double(completed) / Double(total)
    }

    // MARK: - Private

    private func dominantStatus(in subagents: [Subagent]) -> SubagentStatus? {
        Self.resolveDominantStatus(in: subagents)
    }

    private func startActivity(
        sessionId: String,
        count: Int,
        status: SubagentStatus?
    ) async {
        let taskId = activityIdProvider()
        let title = String(localized: "liveactivity.subagent.title")
        await manager.startTask(
            taskId: taskId,
            taskTitle: title,
            projectName: String(localized: "liveactivity.subagent.project")
        )
        trackedActivityTaskId = taskId
        trackedSessionId = sessionId
        logger.info("Subagent Live Activity baslatildi: session=\(sessionId), count=\(count)")

        await manager.updateTask(
            taskId: taskId,
            status: Self.statusKey(for: status),
            currentStep: stepText(activeCount: count, status: status),
            progress: 0.0,
            completedSteps: 0,
            totalSteps: max(count, 1),
            phaseIcon: Self.phaseIcon(for: status),
            estimatedSeconds: nil
        )
    }

    private func updateActivity(
        count: Int,
        status: SubagentStatus?,
        totalCount: Int
    ) async {
        guard let taskId = trackedActivityTaskId else { return }
        let completed = max(totalCount - count, 0)
        await manager.updateTask(
            taskId: taskId,
            status: Self.statusKey(for: status),
            currentStep: stepText(activeCount: count, status: status),
            progress: Self.progress(active: count, completed: completed),
            completedSteps: completed,
            totalSteps: max(totalCount, 1),
            phaseIcon: Self.phaseIcon(for: status),
            estimatedSeconds: nil
        )
    }

    private func scheduleDismiss() {
        cancelPendingDismiss()
        let delay = autoDismissDelay
        pendingDismissTask = Task { [weak self] in
            try? await Task.sleep(for: delay)
            guard !Task.isCancelled else { return }
            await self?.dismissNow()
        }
    }

    private func cancelPendingDismiss() {
        pendingDismissTask?.cancel()
        pendingDismissTask = nil
    }

    private func resetTracking() {
        trackedActivityTaskId = nil
        trackedSessionId = nil
        lastActiveCount = 0
        lastDominantStatus = nil
    }

    private func stepText(activeCount: Int, status: SubagentStatus?) -> String {
        if activeCount == 0 {
            return String(localized: "liveactivity.subagent.allComplete")
        }
        let template = String(localized: "liveactivity.subagent.activeCount %lld")
        return String.localizedStringWithFormat(template, activeCount)
    }
}
