import Foundation

/// Aktif task'lari getiren use case.
struct GetActiveTasksUseCase: Sendable {
    private let repository: TaskRepository

    init(repository: TaskRepository) {
        self.repository = repository
    }

    func execute() async throws -> [AITask] {
        try await repository.getActiveTasks()
    }
}
