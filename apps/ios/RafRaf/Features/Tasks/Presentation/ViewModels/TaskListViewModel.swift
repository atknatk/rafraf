import Foundation
import os

/// Task listesi ekrani icin ViewModel.
@Observable
@MainActor
final class TaskListViewModel {
    // MARK: - State

    var tasks: [AITask] = []
    var isLoading = false
    var errorMessage: String?

    /// Task listesi bossa true doner.
    var showsEmptyState: Bool {
        tasks.isEmpty
    }

    // MARK: - Dependencies

    private let repository: TaskRepository
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "TaskListViewModel"
    )

    // MARK: - Init

    init(repository: TaskRepository) {
        self.repository = repository
    }

    // MARK: - Actions

    /// Aktif task listesini sunucudan yukler.
    func loadActiveTasks() async {
        isLoading = true
        errorMessage = nil

        do {
            tasks = try await repository.getActiveTasks()
        } catch {
            logger.error("Task listesi yuklenemedi: \(error.localizedDescription)")
            errorMessage = String(localized: "task.error.loadFailed")
            tasks = []
        }

        isLoading = false
    }

    /// Belirtilen task'i iptal eder ve listeden kaldirir.
    func cancelTask(taskId: UUID) async {
        do {
            try await repository.cancelTask(taskId: taskId)
            tasks.removeAll { $0.id == taskId }
        } catch {
            logger.error("Task iptal edilemedi: \(error.localizedDescription)")
            errorMessage = String(localized: "task.error.cancelFailed")
        }
    }

    /// WebSocket'ten gelen task durum guncellemesini isler.
    func handleTaskStatusUpdate(_ updatedTask: AITask) {
        guard let index = tasks.firstIndex(where: { $0.id == updatedTask.id }) else {
            // Bilinmeyen task - listeye ekleme
            return
        }
        tasks[index] = updatedTask
    }

    /// WebSocket'ten gelen task_status mesajini isler.
    func handleTaskStatusUpdate(_ content: TaskStatusContent) {
        guard let taskId = UUID(uuidString: content.taskId) else { return }
        guard let index = tasks.firstIndex(where: { $0.id == taskId }) else {
            // Bilinmeyen task — listede yok, yeniden yukleme tetiklenebilir
            logger.info("Task status update for unknown task: \(content.taskId)")
            return
        }

        let existing = tasks[index]
        let newStatus = TaskStatus(rawValue: content.status) ?? existing.status
        tasks[index] = AITask(
            id: existing.id,
            title: existing.title,
            prompt: existing.prompt,
            taskType: existing.taskType,
            status: newStatus,
            currentStep: content.currentStep ?? existing.currentStep,
            totalSteps: content.totalSteps,
            completedSteps: content.completedSteps,
            progressPct: content.progressPct,
            resultSummary: content.detail ?? existing.resultSummary,
            errorMessage: existing.errorMessage,
            projectName: existing.projectName,
            createdAt: existing.createdAt,
            startedAt: existing.startedAt,
            completedAt: existing.completedAt
        )
    }

    /// Hata mesajini temizler.
    func dismissError() {
        errorMessage = nil
    }
}
