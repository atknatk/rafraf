import Foundation

/// Bir task'i iptal eden use case.
struct CancelTaskUseCase: Sendable {
    private let repository: TaskRepository

    init(repository: TaskRepository) {
        self.repository = repository
    }

    func execute(taskId: UUID) async throws {
        try await repository.cancelTask(taskId: taskId)
    }
}
