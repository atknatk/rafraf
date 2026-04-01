import Foundation

/// Task verilerine erisim icin repository protokolu.
protocol TaskRepository: Sendable {
    /// Aktif task'lari getirir.
    func getActiveTasks() async throws -> [AITask]

    /// Belirli bir task'in detayini getirir.
    func getTaskDetail(taskId: UUID) async throws -> AITask

    /// Yeni bir task olusturur.
    func createTask(
        title: String,
        prompt: String,
        taskType: String,
        projectId: UUID?
    ) async throws -> AITask

    /// Bir task'i iptal eder.
    func cancelTask(taskId: UUID) async throws

    /// Live Activity push token'ini kaydeder.
    func registerLiveActivityToken(taskId: UUID, pushToken: String) async throws
}
