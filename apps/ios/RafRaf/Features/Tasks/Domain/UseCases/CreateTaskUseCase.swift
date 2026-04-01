import Foundation

/// Yeni task olusturan use case.
struct CreateTaskUseCase: Sendable {
    private let repository: TaskRepository

    init(repository: TaskRepository) {
        self.repository = repository
    }

    func execute(
        title: String,
        prompt: String,
        taskType: String,
        projectId: UUID?
    ) async throws -> AITask {
        try await repository.createTask(
            title: title,
            prompt: prompt,
            taskType: taskType,
            projectId: projectId
        )
    }
}
