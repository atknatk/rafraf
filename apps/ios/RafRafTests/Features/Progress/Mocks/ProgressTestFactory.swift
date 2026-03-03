import Foundation
@testable import RafRaf

/// Progress feature test data factory.
enum ProgressTestFactory {
    static func createStep(
        id: String = "step-1",
        type: ProgressStepType = .thinking,
        label: String = "Test adimi",
        status: ProgressStepStatus = .pending,
        durationSeconds: Double? = nil,
        detail: String? = nil
    ) -> ProgressStep {
        ProgressStep(
            id: id,
            type: type,
            label: label,
            status: status,
            durationSeconds: durationSeconds,
            detail: detail
        )
    }

    static func createState(
        id: String = "progress-1",
        mode: ProgressMode = .determinate,
        percentage: Int = 50,
        taskDescription: String = "Test gorevi",
        steps: [ProgressStep] = [],
        currentStepIndex: Int? = nil,
        status: ProgressOverallStatus = .running
    ) -> ProgressState {
        ProgressState(
            id: id,
            mode: mode,
            percentage: percentage,
            taskDescription: taskDescription,
            steps: steps,
            currentStepIndex: currentStepIndex,
            status: status
        )
    }

    static func createProgressEvent(
        task: String = "Build",
        step: Int = 2,
        totalSteps: Int = 5,
        percentage: Int = 40,
        details: String? = nil
    ) -> ProgressEventDTO {
        ProgressEventDTO(
            task: task,
            step: step,
            totalSteps: totalSteps,
            percentage: percentage,
            details: details
        )
    }

    static func createProgressStateDTO(
        id: String = "dto-1",
        mode: String? = "determinate",
        percentage: Int = 60,
        taskDescription: String = "DTO gorevi",
        steps: [ProgressStepDTO]? = nil,
        currentStepIndex: Int? = nil,
        status: String? = "running"
    ) -> ProgressStateDTO {
        ProgressStateDTO(
            id: id,
            mode: mode,
            percentage: percentage,
            taskDescription: taskDescription,
            steps: steps,
            currentStepIndex: currentStepIndex,
            status: status
        )
    }

    static func createStepDTO(
        id: String = "step-dto-1",
        type: String = "thinking",
        label: String = "DTO adimi",
        status: String = "pending",
        durationSeconds: Double? = nil,
        detail: String? = nil
    ) -> ProgressStepDTO {
        ProgressStepDTO(
            id: id,
            type: type,
            label: label,
            status: status,
            durationSeconds: durationSeconds,
            detail: detail
        )
    }

    /// 3 adimli ornek state olusturur (1 completed, 1 active, 1 pending).
    static func createThreeStepState() -> ProgressState {
        let steps = [
            createStep(id: "s1", type: .thinking, label: "Analiz", status: .completed, durationSeconds: 1.5),
            createStep(id: "s2", type: .toolCalling, label: "Build", status: .active, detail: "docker build"),
            createStep(id: "s3", type: .generating, label: "Sonuc", status: .pending),
        ]
        return createState(
            percentage: 45,
            taskDescription: "Proje derleniyor",
            steps: steps,
            currentStepIndex: 1
        )
    }
}
