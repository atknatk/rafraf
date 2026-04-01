import Foundation
@testable import RafRaf

/// Test icin mock task repository.
final class MockTaskRepository: TaskRepository, @unchecked Sendable {

    // MARK: - Results

    var getActiveTasksResult: Result<[AITask], Error> = .success([])
    var getTaskDetailResult: Result<AITask, Error> = .success(
        TaskTestFactory.createTask()
    )
    var createTaskResult: Result<AITask, Error> = .success(
        TaskTestFactory.createTask(status: .queued)
    )
    var cancelTaskResult: Result<Void, Error> = .success(())
    var registerLiveActivityTokenResult: Result<Void, Error> = .success(())

    // MARK: - Call Tracking

    var getActiveTasksCallCount = 0
    var getTaskDetailCallCount = 0
    var createTaskCallCount = 0
    var cancelTaskCallCount = 0
    var registerLiveActivityTokenCallCount = 0

    var lastTaskId: UUID?
    var lastCreateTitle: String?
    var lastCreatePrompt: String?
    var lastCreateTaskType: String?
    var lastCreateProjectId: UUID?
    var lastPushToken: String?

    // MARK: - Protocol Methods

    func getActiveTasks() async throws -> [AITask] {
        getActiveTasksCallCount += 1
        return try getActiveTasksResult.get()
    }

    func getTaskDetail(taskId: UUID) async throws -> AITask {
        getTaskDetailCallCount += 1
        lastTaskId = taskId
        return try getTaskDetailResult.get()
    }

    func createTask(
        title: String,
        prompt: String,
        taskType: String,
        projectId: UUID?
    ) async throws -> AITask {
        createTaskCallCount += 1
        lastCreateTitle = title
        lastCreatePrompt = prompt
        lastCreateTaskType = taskType
        lastCreateProjectId = projectId
        return try createTaskResult.get()
    }

    func cancelTask(taskId: UUID) async throws {
        cancelTaskCallCount += 1
        lastTaskId = taskId
        try cancelTaskResult.get()
    }

    func registerLiveActivityToken(taskId: UUID, pushToken: String) async throws {
        registerLiveActivityTokenCallCount += 1
        lastTaskId = taskId
        lastPushToken = pushToken
        try registerLiveActivityTokenResult.get()
    }
}
