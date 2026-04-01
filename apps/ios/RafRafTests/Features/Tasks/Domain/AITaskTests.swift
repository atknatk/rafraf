import Foundation
import Testing
@testable import RafRaf

/// AITask domain model testleri — creation, JSON round-trip, computed properties.
@Suite("AITask Domain Model Tests")
struct AITaskTests {

    // MARK: - Helpers

    private func makeSampleTask(
        id: UUID = UUID(),
        title: String = "Implement login feature",
        prompt: String = "Add login screen with email/password",
        taskType: String = "feature",
        status: TaskStatus = .implementing,
        currentStep: String? = "developer",
        totalSteps: Int = 4,
        completedSteps: Int = 1,
        progressPct: Int = 35,
        resultSummary: String? = nil,
        errorMessage: String? = nil,
        projectName: String? = "MyProject",
        createdAt: Date = Date(),
        startedAt: Date? = Date(),
        completedAt: Date? = nil
    ) -> AITask {
        AITask(
            id: id,
            title: title,
            prompt: prompt,
            taskType: taskType,
            status: status,
            currentStep: currentStep,
            totalSteps: totalSteps,
            completedSteps: completedSteps,
            progressPct: progressPct,
            resultSummary: resultSummary,
            errorMessage: errorMessage,
            projectName: projectName,
            createdAt: createdAt,
            startedAt: startedAt,
            completedAt: completedAt
        )
    }

    // MARK: - Creation

    @Test("AITask tum alanlarla olusturulabilmeli")
    func creation() {
        let id = UUID()
        let now = Date()
        let task = makeSampleTask(
            id: id,
            title: "Test task",
            prompt: "Do something",
            taskType: "bugfix",
            status: .queued,
            currentStep: nil,
            totalSteps: 3,
            completedSteps: 0,
            progressPct: 0,
            resultSummary: nil,
            errorMessage: nil,
            projectName: "TestProject",
            createdAt: now,
            startedAt: nil,
            completedAt: nil
        )

        #expect(task.id == id)
        #expect(task.title == "Test task")
        #expect(task.prompt == "Do something")
        #expect(task.taskType == "bugfix")
        #expect(task.status == .queued)
        #expect(task.currentStep == nil)
        #expect(task.totalSteps == 3)
        #expect(task.completedSteps == 0)
        #expect(task.progressPct == 0)
        #expect(task.resultSummary == nil)
        #expect(task.errorMessage == nil)
        #expect(task.projectName == "TestProject")
        #expect(task.createdAt == now)
        #expect(task.startedAt == nil)
        #expect(task.completedAt == nil)
    }

    @Test("AITask completed durumdaki task'ta resultSummary olmali")
    func completedTaskWithSummary() {
        let task = makeSampleTask(
            status: .completed,
            completedSteps: 4,
            progressPct: 100,
            resultSummary: "Feature implemented successfully",
            completedAt: Date()
        )

        #expect(task.status == .completed)
        #expect(task.resultSummary == "Feature implemented successfully")
        #expect(task.completedAt != nil)
    }

    @Test("AITask failed durumdaki task'ta errorMessage olmali")
    func failedTaskWithError() {
        let task = makeSampleTask(
            status: .failed,
            errorMessage: "Build failed: missing dependency",
            completedAt: Date()
        )

        #expect(task.status == .failed)
        #expect(task.errorMessage == "Build failed: missing dependency")
    }

    // MARK: - JSON Decode Round-trip

    @Test("AITask JSON encode/decode round-trip basarili olmali")
    func jsonDecodeRoundtrip() throws {
        let id = UUID()
        let now = Date()
        let original = makeSampleTask(
            id: id,
            title: "Round trip test",
            prompt: "Test prompt",
            taskType: "feature",
            status: .testing,
            currentStep: "tester",
            totalSteps: 4,
            completedSteps: 2,
            progressPct: 60,
            resultSummary: nil,
            errorMessage: nil,
            projectName: "TestProject",
            createdAt: now,
            startedAt: now,
            completedAt: nil
        )

        let encoder = JSONEncoder()
        let decoder = JSONDecoder()

        let data = try encoder.encode(original)
        let decoded = try decoder.decode(AITask.self, from: data)

        #expect(decoded.id == original.id)
        #expect(decoded.title == original.title)
        #expect(decoded.prompt == original.prompt)
        #expect(decoded.taskType == original.taskType)
        #expect(decoded.status == original.status)
        #expect(decoded.currentStep == original.currentStep)
        #expect(decoded.totalSteps == original.totalSteps)
        #expect(decoded.completedSteps == original.completedSteps)
        #expect(decoded.progressPct == original.progressPct)
        #expect(decoded.projectName == original.projectName)
    }

    @Test("AITask snake_case JSON key'leri ile decode edilebilmeli")
    func snakeCaseJsonDecode() throws {
        let taskId = UUID()
        let json = """
        {
            "id": "\(taskId.uuidString)",
            "title": "Backend task",
            "prompt": "Fix the bug",
            "task_type": "bugfix",
            "status": "implementing",
            "current_step": "developer",
            "total_steps": 4,
            "completed_steps": 1,
            "progress_pct": 25,
            "result_summary": null,
            "error_message": null,
            "project_name": "RafRaf",
            "created_at": "2026-04-01T10:00:00Z",
            "started_at": "2026-04-01T10:01:00Z",
            "completed_at": null
        }
        """

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601

        let data = Data(json.utf8)
        let task = try decoder.decode(AITask.self, from: data)

        #expect(task.id == taskId)
        #expect(task.title == "Backend task")
        #expect(task.taskType == "bugfix")
        #expect(task.status == .implementing)
        #expect(task.currentStep == "developer")
        #expect(task.totalSteps == 4)
        #expect(task.completedSteps == 1)
        #expect(task.progressPct == 25)
        #expect(task.projectName == "RafRaf")
        #expect(task.resultSummary == nil)
        #expect(task.errorMessage == nil)
        #expect(task.completedAt == nil)
    }

    // MARK: - progressFraction

    @Test("AITask progressFraction 0-1 arasi degere donusmeli")
    func progressFraction() {
        let task75 = makeSampleTask(progressPct: 75)
        #expect(task75.progressFraction == 0.75)

        let task0 = makeSampleTask(progressPct: 0)
        #expect(task0.progressFraction == 0.0)

        let task100 = makeSampleTask(progressPct: 100)
        #expect(task100.progressFraction == 1.0)
    }

    @Test("AITask progressFraction 50 icin 0.5 donmeli")
    func progressFractionMidpoint() {
        let task = makeSampleTask(progressPct: 50)
        #expect(task.progressFraction == 0.5)
    }

    // MARK: - stepProgress

    @Test("AITask stepProgress dogru hesaplanmali")
    func stepProgress() {
        let task = makeSampleTask(totalSteps: 4, completedSteps: 2)
        #expect(task.stepProgress == 0.5)
    }

    @Test("AITask stepProgress 0 step tamamlandiginda 0 olmali")
    func stepProgressZero() {
        let task = makeSampleTask(totalSteps: 4, completedSteps: 0)
        #expect(task.stepProgress == 0.0)
    }

    @Test("AITask stepProgress tum step'ler tamamlandiginda 1.0 olmali")
    func stepProgressComplete() {
        let task = makeSampleTask(totalSteps: 4, completedSteps: 4)
        #expect(task.stepProgress == 1.0)
    }

    @Test("AITask stepProgress totalSteps 0 oldugunda 0 donmeli")
    func stepProgressZeroTotal() {
        let task = makeSampleTask(totalSteps: 0, completedSteps: 0)
        #expect(task.stepProgress == 0.0)
    }

    // MARK: - Equatable / Identifiable

    @Test("AITask ayni id ile olusturulan task'lar esit olmali")
    func equatable() {
        let id = UUID()
        let task1 = makeSampleTask(id: id)
        let task2 = makeSampleTask(id: id)
        #expect(task1.id == task2.id)
    }

    @Test("AITask farkli id ile olusturulan task'lar farkli olmali")
    func notEqual() {
        let task1 = makeSampleTask(id: UUID())
        let task2 = makeSampleTask(id: UUID())
        #expect(task1.id != task2.id)
    }
}
