import Foundation
import os

/// TaskRepository protokolunun REST API implementasyonu.
final class TaskRepositoryImpl: TaskRepository, @unchecked Sendable {
    private let networkClient: MockableNetworkClient
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "TaskRepositoryImpl"
    )

    init(networkClient: MockableNetworkClient) {
        self.networkClient = networkClient
    }

    func getActiveTasks() async throws -> [AITask] {
        let data = try await networkClient.get(path: "/api/v1/tasks/active")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode([AITask].self, from: data)
    }

    func getTaskDetail(taskId: UUID) async throws -> AITask {
        let data = try await networkClient.get(path: "/api/v1/tasks/\(taskId.uuidString)")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(AITask.self, from: data)
    }

    func createTask(
        title: String,
        prompt: String,
        taskType: String,
        projectId: UUID?
    ) async throws -> AITask {
        let requestBody = CreateTaskRequestDTO(
            title: title,
            prompt: prompt,
            taskType: taskType,
            projectId: projectId
        )
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let body = try encoder.encode(requestBody)

        let data = try await networkClient.post(path: "/api/v1/tasks", body: body)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(AITask.self, from: data)
    }

    func cancelTask(taskId: UUID) async throws {
        _ = try await networkClient.post(
            path: "/api/v1/tasks/\(taskId.uuidString)/cancel",
            body: nil
        )
    }

    func registerLiveActivityToken(taskId: UUID, pushToken: String) async throws {
        let requestBody = LiveActivityTokenDTO(pushToken: pushToken)
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let body = try encoder.encode(requestBody)

        _ = try await networkClient.patch(
            path: "/api/v1/tasks/\(taskId.uuidString)/live-activity",
            body: body
        )
    }
}

/// Network istemcisi icin mocklanabilir protokol.
/// Test'lerde MockNetworkClient bu protokole uyar.
protocol MockableNetworkClient: Sendable {
    func get(path: String) async throws -> Data
    func post(path: String, body: Data?) async throws -> Data
    func patch(path: String, body: Data?) async throws -> Data
}
