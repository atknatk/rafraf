import Foundation
@testable import RafRaf

/// Task testleri icin factory helper.
enum TaskTestFactory {

    static func createTask(
        id: UUID = UUID(),
        title: String = "Test task",
        prompt: String = "Test prompt",
        taskType: String = "feature",
        status: TaskStatus = .implementing,
        currentStep: String? = "developer",
        totalSteps: Int = 4,
        completedSteps: Int = 1,
        progressPct: Int = 25,
        resultSummary: String? = nil,
        errorMessage: String? = nil,
        projectName: String? = "TestProject",
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

    static func createTaskList(count: Int = 3) -> [AITask] {
        (0..<count).map { index in
            createTask(
                id: UUID(),
                title: "Task \(index + 1)",
                completedSteps: index,
                progressPct: index * 25
            )
        }
    }

    static func createCompletedTask(id: UUID = UUID()) -> AITask {
        createTask(
            id: id,
            status: .completed,
            currentStep: nil,
            completedSteps: 4,
            progressPct: 100,
            resultSummary: "Task completed successfully",
            completedAt: Date()
        )
    }

    static func createFailedTask(id: UUID = UUID()) -> AITask {
        createTask(
            id: id,
            status: .failed,
            errorMessage: "Build failed: compilation error",
            completedAt: Date()
        )
    }
}
