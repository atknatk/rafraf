import Foundation
import Testing
@testable import RafRaf

/// ProgressStep ve ProgressState domain model testleri.
@Suite("Progress Domain Model Tests")
struct ProgressModelTests {

    // MARK: - ProgressStep

    @Test("ProgressStep varsayilan degerleri dogru olmali")
    func stepDefaults() {
        let step = ProgressStep(type: .thinking, label: "Analiz")

        #expect(!step.id.isEmpty)
        #expect(step.type == .thinking)
        #expect(step.label == "Analiz")
        #expect(step.status == .pending)
        #expect(step.durationSeconds == nil)
        #expect(step.detail == nil)
        #expect(step.toolName == nil)
    }

    @Test("ProgressStep toolName alanini dogru saklamali")
    func stepToolNameField() {
        let step = ProgressStep(
            type: .toolCalling,
            label: String(localized: "Bash calistiriliyor"),
            toolName: "Bash"
        )

        #expect(step.toolName == "Bash")
        #expect(step.type == .toolCalling)
    }

    @Test("ProgressStep toolName nil oldugunda nil olmali")
    func stepToolNameNil() {
        let step = ProgressStep(type: .thinking, label: "Dusunuyor")

        #expect(step.toolName == nil)
    }

    @Test("ProgressStep toolName ile Equatable dogru calismali")
    func stepEquatableWithToolName() {
        let step1 = ProgressStep(id: "s1", type: .toolCalling, label: "A", toolName: "Read")
        let step2 = ProgressStep(id: "s1", type: .toolCalling, label: "A", toolName: "Read")
        let step3 = ProgressStep(id: "s1", type: .toolCalling, label: "A", toolName: "Bash")

        #expect(step1 == step2)
        #expect(step1 != step3)
    }

    @Test("ProgressStep tum tip degerleri dogru olmali")
    func stepTypes() {
        let types: [ProgressStepType] = [.thinking, .toolCalling, .generating, .waitingApproval]
        #expect(types.count == 4)
        #expect(ProgressStepType.allCases.count == 4)
    }

    @Test("ProgressStep tum durum degerleri dogru olmali")
    func stepStatuses() {
        let statuses: [ProgressStepStatus] = [.pending, .active, .completed, .failed]
        #expect(statuses.count == 4)
        #expect(ProgressStepStatus.allCases.count == 4)
    }

    @Test("ProgressStep Equatable dogru calismali")
    func stepEquatable() {
        let step1 = ProgressStep(id: "s1", type: .thinking, label: "A", status: .pending)
        let step2 = ProgressStep(id: "s1", type: .thinking, label: "A", status: .pending)
        let step3 = ProgressStep(id: "s2", type: .thinking, label: "A", status: .pending)

        #expect(step1 == step2)
        #expect(step1 != step3)
    }

    @Test("ProgressStep Identifiable id dogru donmeli")
    func stepIdentifiable() {
        let step = ProgressStep(id: "test-id", type: .generating, label: "Gen")
        #expect(step.id == "test-id")
    }

    @Test("ProgressStep ozel degerlerle olusturulabilmeli")
    func stepCustomValues() {
        let step = ProgressStep(
            id: "custom",
            type: .toolCalling,
            label: "Docker build",
            status: .active,
            durationSeconds: 3.5,
            detail: "docker build --tag app",
            toolName: "Bash"
        )

        #expect(step.id == "custom")
        #expect(step.type == .toolCalling)
        #expect(step.label == "Docker build")
        #expect(step.status == .active)
        #expect(step.durationSeconds == 3.5)
        #expect(step.detail == "docker build --tag app")
        #expect(step.toolName == "Bash")
    }

    @Test("ProgressStepType rawValue dogru olmali")
    func stepTypeRawValues() {
        #expect(ProgressStepType.thinking.rawValue == "thinking")
        #expect(ProgressStepType.toolCalling.rawValue == "tool_calling")
        #expect(ProgressStepType.generating.rawValue == "generating")
        #expect(ProgressStepType.waitingApproval.rawValue == "waiting_approval")
    }

    @Test("ProgressStepStatus rawValue dogru olmali")
    func stepStatusRawValues() {
        #expect(ProgressStepStatus.pending.rawValue == "pending")
        #expect(ProgressStepStatus.active.rawValue == "active")
        #expect(ProgressStepStatus.completed.rawValue == "completed")
        #expect(ProgressStepStatus.failed.rawValue == "failed")
    }

    // MARK: - ProgressState

    @Test("ProgressState varsayilan degerleri dogru olmali")
    func stateDefaults() {
        let state = ProgressState(taskDescription: "Test gorevi")

        #expect(!state.id.isEmpty)
        #expect(state.mode == .indeterminate)
        #expect(state.percentage == 0)
        #expect(state.taskDescription == "Test gorevi")
        #expect(state.steps.isEmpty)
        #expect(state.currentStepIndex == nil)
        #expect(state.status == .running)
    }

    @Test("ProgressState tum mod degerleri dogru olmali")
    func stateModes() {
        #expect(ProgressMode.allCases.count == 2)
        #expect(ProgressMode.determinate.rawValue == "determinate")
        #expect(ProgressMode.indeterminate.rawValue == "indeterminate")
    }

    @Test("ProgressState tum overall status degerleri dogru olmali")
    func stateOverallStatuses() {
        #expect(ProgressOverallStatus.allCases.count == 4)
        #expect(ProgressOverallStatus.running.rawValue == "running")
        #expect(ProgressOverallStatus.completed.rawValue == "completed")
        #expect(ProgressOverallStatus.failed.rawValue == "failed")
        #expect(ProgressOverallStatus.cancelled.rawValue == "cancelled")
    }

    @Test("ProgressState Equatable dogru calismali")
    func stateEquatable() {
        let state1 = ProgressState(id: "p1", percentage: 50, taskDescription: "A")
        let state2 = ProgressState(id: "p1", percentage: 50, taskDescription: "A")
        let state3 = ProgressState(id: "p2", percentage: 50, taskDescription: "A")

        #expect(state1 == state2)
        #expect(state1 != state3)
    }

    @Test("ProgressState step'lerle olusturulabilmeli")
    func stateWithSteps() {
        let steps = [
            ProgressTestFactory.createStep(id: "s1", status: .completed),
            ProgressTestFactory.createStep(id: "s2", status: .active),
            ProgressTestFactory.createStep(id: "s3", status: .pending),
        ]

        let state = ProgressState(
            mode: .determinate,
            percentage: 40,
            taskDescription: "Multi-step gorev",
            steps: steps,
            currentStepIndex: 1
        )

        #expect(state.steps.count == 3)
        #expect(state.currentStepIndex == 1)
        #expect(state.mode == .determinate)
    }
}
