import Foundation
import os

/// Progress ViewModel.
/// AI islem ilerleme durumunu yonetir, animasyon ve step-by-step gostergeyi kontrol eder.
@Observable
@MainActor
final class ProgressViewModel {
    // MARK: - State

    /// Mevcut ilerleme durumu.
    var progressState: ProgressState?
    /// Progress gorunur mu (animasyon icin).
    var isVisible: Bool = false
    /// Hata mesaji.
    var errorMessage: String?

    // MARK: - Computed

    /// Ilerleme aktif mi.
    var isActive: Bool {
        guard let state = progressState else { return false }
        return state.status == .running
    }

    /// Ilerleme yuzdesi (0.0 - 1.0).
    var progressFraction: Double {
        guard let state = progressState else { return 0.0 }
        return Double(state.percentage) / 100.0
    }

    /// Mevcut aktif adim.
    var currentStep: ProgressStep? {
        guard let state = progressState,
              let index = state.currentStepIndex,
              index >= 0,
              index < state.steps.count else {
            return nil
        }
        return state.steps[index]
    }

    /// Determinate mod mu.
    var isDeterminate: Bool {
        progressState?.mode == .determinate
    }

    /// Tamamlanan adim sayisi.
    var completedStepCount: Int {
        progressState?.steps.filter { $0.status == .completed }.count ?? 0
    }

    /// Toplam adim sayisi.
    var totalStepCount: Int {
        progressState?.steps.count ?? 0
    }

    /// Gorev aciklamasi.
    var taskDescription: String {
        progressState?.taskDescription ?? ""
    }

    // MARK: - Private

    private let observeProgressUseCase: ObserveProgressUseCase
    private let logger = AppLogger.logger(for: "Progress")

    // MARK: - Init

    init(observeProgressUseCase: ObserveProgressUseCase) {
        self.observeProgressUseCase = observeProgressUseCase
    }

    // MARK: - Actions

    /// Yeni ilerleme durumunu gunceller.
    /// WebSocket handler'dan cagirilir.
    /// - Parameter state: Yeni ilerleme durumu
    func updateProgress(_ state: ProgressState) {
        progressState = state

        if state.status == .running {
            isVisible = true

            // Live Activity guncelle
            let activeTool = state.steps.first(where: { $0.status == .active })?.label ?? state.taskDescription
            LiveActivityManager.shared.update(
                tool: activeTool,
                percentage: state.percentage,
                phaseLabel: state.taskDescription
            )
        } else if state.status == .completed {
            LiveActivityManager.shared.end()
        }

        logger.info("Progress guncellendi: \(state.percentage)% - \(state.taskDescription)")
    }

    /// Basit progress event'inden ilerleme gunceller.
    /// ProgressMessageContent'ten donusturulen ProgressState icin.
    /// - Parameters:
    ///   - task: Gorev aciklamasi
    ///   - step: Mevcut adim numarasi
    ///   - totalSteps: Toplam adim sayisi
    ///   - percentage: Ilerleme yuzdesi
    ///   - details: Ek detay
    func updateFromEvent(
        task: String,
        step: Int,
        totalSteps: Int,
        percentage: Int,
        details: String?
    ) {
        let mode: ProgressMode = totalSteps > 0 ? .determinate : .indeterminate
        let status: ProgressOverallStatus = percentage >= 100 ? .completed : .running

        var steps: [ProgressStep] = []
        if totalSteps > 0 {
            steps = (1...totalSteps).map { index in
                let stepStatus: ProgressStepStatus
                if index < step {
                    stepStatus = .completed
                } else if index == step {
                    stepStatus = .active
                } else {
                    stepStatus = .pending
                }
                return ProgressStep(
                    id: "step-\(index)",
                    type: .thinking,
                    label: String(localized: "progress.step.label.\(index)"),
                    status: stepStatus,
                    detail: index == step ? details : nil
                )
            }
        }

        let state = ProgressState(
            mode: mode,
            percentage: percentage,
            taskDescription: task,
            steps: steps,
            currentStepIndex: step > 0 ? step - 1 : nil,
            status: status
        )

        updateProgress(state)
    }

    /// Tool calisma durumunu gunceller.
    /// action_result mesajlarindan cagirilir.
    /// - Parameters:
    ///   - toolName: Tool adi
    ///   - action: Yapilan islem
    ///   - isRunning: Tool calisiyor mu
    func updateToolStatus(toolName: String, action: String, isRunning: Bool) {
        guard var state = progressState else { return }

        // Mevcut aktif step'i guncelle
        let updatedSteps = state.steps.map { step in
            if step.status == .active {
                return ProgressStep(
                    id: step.id,
                    type: .toolCalling,
                    label: step.label,
                    status: isRunning ? .active : .completed,
                    durationSeconds: step.durationSeconds,
                    detail: "\(toolName): \(action)"
                )
            }
            return step
        }

        let updatedState = ProgressState(
            id: state.id,
            mode: state.mode,
            percentage: state.percentage,
            taskDescription: state.taskDescription,
            steps: updatedSteps,
            currentStepIndex: state.currentStepIndex,
            status: state.status
        )

        progressState = updatedState
        logger.info("Tool durumu guncellendi: \(toolName) - \(action)")
    }

    /// Ilerlemeyi tamamlanmis olarak isaretler.
    func markCompleted() {
        guard let state = progressState else { return }

        let completedSteps = state.steps.map { step in
            ProgressStep(
                id: step.id,
                type: step.type,
                label: step.label,
                status: .completed,
                durationSeconds: step.durationSeconds,
                detail: step.detail
            )
        }

        progressState = ProgressState(
            id: state.id,
            mode: state.mode,
            percentage: 100,
            taskDescription: state.taskDescription,
            steps: completedSteps,
            currentStepIndex: nil,
            status: .completed
        )

        logger.info("Progress tamamlandi")

        // Kisa bir gecikme sonrasi gizle
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(2))
            self.dismiss()
        }
    }

    /// Ilerlemeyi basarisiz olarak isaretler.
    /// - Parameter error: Hata mesaji
    func markFailed(error: String) {
        if let state = progressState {
            progressState = ProgressState(
                id: state.id,
                mode: state.mode,
                percentage: state.percentage,
                taskDescription: state.taskDescription,
                steps: state.steps,
                currentStepIndex: state.currentStepIndex,
                status: .failed
            )
        }

        errorMessage = error
        logger.error("Progress basarisiz: \(error)")
    }

    /// Ilerleme gostergesini kapatir.
    func dismiss() {
        isVisible = false

        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(500))
            self.progressState = nil
            self.errorMessage = nil
        }
    }

    /// Hata mesajini temizler.
    func dismissError() {
        errorMessage = nil
    }
}
