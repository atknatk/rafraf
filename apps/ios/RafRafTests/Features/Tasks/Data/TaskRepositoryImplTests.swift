import Foundation
import Testing
@testable import RafRaf

/// TaskRepositoryImpl testleri — REST API response parse, payload dogrulama.
@Suite("TaskRepositoryImpl Tests")
struct TaskRepositoryImplTests {

    // MARK: - GET /api/v1/tasks/active

    @Test("getActiveTasks bos liste donuldugunde bos array donmeli")
    func getActiveTasks_emptyResponse() async throws {
        let mockNetwork = MockNetworkClient()
        mockNetwork.getResult = .success(Data("[]".utf8))
        let repo = TaskRepositoryImpl(networkClient: mockNetwork)

        let tasks = try await repo.getActiveTasks()

        #expect(tasks.isEmpty)
        #expect(mockNetwork.getCallCount == 1)
        #expect(mockNetwork.lastGetPath == "/api/v1/tasks/active")
    }

    @Test("getActiveTasks JSON response'u [AITask] olarak decode etmeli")
    func getActiveTasks_decodesResponse() async throws {
        let taskId = UUID()
        let json = """
        [
            {
                "id": "\(taskId.uuidString)",
                "title": "Implement feature",
                "prompt": "Add login screen",
                "task_type": "feature",
                "status": "implementing",
                "current_step": "developer",
                "total_steps": 4,
                "completed_steps": 1,
                "progress_pct": 30,
                "result_summary": null,
                "error_message": null,
                "project_name": "RafRaf",
                "created_at": "2026-04-01T10:00:00Z",
                "started_at": "2026-04-01T10:01:00Z",
                "completed_at": null
            }
        ]
        """

        let mockNetwork = MockNetworkClient()
        mockNetwork.getResult = .success(Data(json.utf8))
        let repo = TaskRepositoryImpl(networkClient: mockNetwork)

        let tasks = try await repo.getActiveTasks()

        #expect(tasks.count == 1)
        #expect(tasks[0].id == taskId)
        #expect(tasks[0].title == "Implement feature")
        #expect(tasks[0].status == .implementing)
        #expect(tasks[0].progressPct == 30)
    }

    // MARK: - GET /api/v1/tasks/{id}

    @Test("getTaskDetail tek AITask decode etmeli")
    func getTaskDetail_decodesResponse() async throws {
        let taskId = UUID()
        let json = """
        {
            "id": "\(taskId.uuidString)",
            "title": "Fix bug",
            "prompt": "Fix the crash on launch",
            "task_type": "bugfix",
            "status": "testing",
            "current_step": "tester",
            "total_steps": 4,
            "completed_steps": 2,
            "progress_pct": 60,
            "result_summary": null,
            "error_message": null,
            "project_name": "RafRaf",
            "created_at": "2026-04-01T10:00:00Z",
            "started_at": "2026-04-01T10:01:00Z",
            "completed_at": null
        }
        """

        let mockNetwork = MockNetworkClient()
        mockNetwork.getResult = .success(Data(json.utf8))
        let repo = TaskRepositoryImpl(networkClient: mockNetwork)

        let task = try await repo.getTaskDetail(taskId: taskId)

        #expect(task.id == taskId)
        #expect(task.title == "Fix bug")
        #expect(task.status == .testing)
        #expect(task.currentStep == "tester")
        #expect(mockNetwork.lastGetPath == "/api/v1/tasks/\(taskId.uuidString)")
    }

    // MARK: - POST /api/v1/tasks

    @Test("createTask dogru payload gondermeli")
    func createTask_sendsCorrectPayload() async throws {
        let projectId = UUID()
        let responseTaskId = UUID()
        let responseJson = """
        {
            "id": "\(responseTaskId.uuidString)",
            "title": "New feature",
            "prompt": "Build the dashboard",
            "task_type": "feature",
            "status": "queued",
            "current_step": null,
            "total_steps": 4,
            "completed_steps": 0,
            "progress_pct": 0,
            "result_summary": null,
            "error_message": null,
            "project_name": "RafRaf",
            "created_at": "2026-04-01T10:00:00Z",
            "started_at": null,
            "completed_at": null
        }
        """

        let mockNetwork = MockNetworkClient()
        mockNetwork.postResult = .success(Data(responseJson.utf8))
        let repo = TaskRepositoryImpl(networkClient: mockNetwork)

        let task = try await repo.createTask(
            title: "New feature",
            prompt: "Build the dashboard",
            taskType: "feature",
            projectId: projectId
        )

        #expect(task.id == responseTaskId)
        #expect(task.status == .queued)
        #expect(mockNetwork.postCallCount == 1)
        #expect(mockNetwork.lastPostPath == "/api/v1/tasks")

        // Body dogrulama: title, prompt, task_type, project_id olmali
        if let body = mockNetwork.lastPostBody,
           let dict = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
            #expect(dict["title"] as? String == "New feature")
            #expect(dict["prompt"] as? String == "Build the dashboard")
            #expect(dict["task_type"] as? String == "feature")
            #expect(dict["project_id"] as? String == projectId.uuidString)
        } else {
            Issue.record("POST body parse edilemedi")
        }
    }

    // MARK: - POST /api/v1/tasks/{id}/cancel

    @Test("cancelTask dogru endpoint'e POST gondermeli")
    func cancelTask_sendsPost() async throws {
        let taskId = UUID()

        let mockNetwork = MockNetworkClient()
        mockNetwork.postResult = .success(Data("{}".utf8))
        let repo = TaskRepositoryImpl(networkClient: mockNetwork)

        try await repo.cancelTask(taskId: taskId)

        #expect(mockNetwork.postCallCount == 1)
        #expect(mockNetwork.lastPostPath == "/api/v1/tasks/\(taskId.uuidString)/cancel")
    }

    // MARK: - PATCH /api/v1/tasks/{id}/live-activity

    @Test("registerLiveActivityToken dogru body ile PATCH gondermeli")
    func registerLiveActivityToken_sendsPatch() async throws {
        let taskId = UUID()
        let token = "abc123def456"

        let mockNetwork = MockNetworkClient()
        mockNetwork.patchResult = .success(Data("{}".utf8))
        let repo = TaskRepositoryImpl(networkClient: mockNetwork)

        try await repo.registerLiveActivityToken(taskId: taskId, pushToken: token)

        #expect(mockNetwork.patchCallCount == 1)
        #expect(mockNetwork.lastPatchPath == "/api/v1/tasks/\(taskId.uuidString)/live-activity")

        if let body = mockNetwork.lastPatchBody,
           let dict = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
            #expect(dict["push_token"] as? String == token)
        } else {
            Issue.record("PATCH body parse edilemedi")
        }
    }

    // MARK: - Error Handling

    @Test("Network hatasi durumunda dogru error firlatmali")
    func networkError_throwsCorrectError() async {
        let mockNetwork = MockNetworkClient()
        mockNetwork.getResult = .failure(RafRafError.networkError)
        let repo = TaskRepositoryImpl(networkClient: mockNetwork)

        do {
            _ = try await repo.getActiveTasks()
            Issue.record("Hata firlatilmasi gerekiyordu")
        } catch {
            #expect(error is RafRafError)
        }
    }

    @Test("Gecersiz JSON response'da decode hatasi firlatmali")
    func invalidJson_throwsDecodeError() async {
        let mockNetwork = MockNetworkClient()
        mockNetwork.getResult = .success(Data("invalid json".utf8))
        let repo = TaskRepositoryImpl(networkClient: mockNetwork)

        do {
            _ = try await repo.getActiveTasks()
            Issue.record("Decode hatasi firlatilmasi gerekiyordu")
        } catch {
            // DecodingError veya RafRafError bekliyoruz
            #expect(error is DecodingError || error is RafRafError)
        }
    }
}

// MARK: - MockNetworkClient

/// TaskRepositoryImpl testleri icin network mock.
/// Gercek NetworkClient actor'unu taklit eder.
final class MockNetworkClient: @unchecked Sendable {

    // GET
    var getResult: Result<Data, Error> = .success(Data())
    var getCallCount = 0
    var lastGetPath: String?

    // POST
    var postResult: Result<Data, Error> = .success(Data())
    var postCallCount = 0
    var lastPostPath: String?
    var lastPostBody: Data?

    // PATCH
    var patchResult: Result<Data, Error> = .success(Data())
    var patchCallCount = 0
    var lastPatchPath: String?
    var lastPatchBody: Data?

    func get(path: String) async throws -> Data {
        getCallCount += 1
        lastGetPath = path
        return try getResult.get()
    }

    func post(path: String, body: Data?) async throws -> Data {
        postCallCount += 1
        lastPostPath = path
        lastPostBody = body
        return try postResult.get()
    }

    func patch(path: String, body: Data?) async throws -> Data {
        patchCallCount += 1
        lastPatchPath = path
        lastPatchBody = body
        return try patchResult.get()
    }
}
