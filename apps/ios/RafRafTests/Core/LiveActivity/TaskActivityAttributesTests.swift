import Foundation
import Testing
@testable import RafRaf

/// TaskActivityAttributes ve ContentState testleri.
@Suite("TaskActivityAttributes Tests")
struct TaskActivityAttributesTests {

    // MARK: - ContentState Codable

    @Test("ContentState encode → decode roundtrip basarili olmali")
    func contentState_codableRoundtrip() throws {
        let state = TaskActivityAttributes.ContentState(
            status: "implementing",
            currentStep: "Developer is writing code...",
            progress: 0.45,
            completedSteps: 2,
            totalSteps: 5,
            estimatedSecondsRemaining: 180,
            phaseIcon: "hammer.fill"
        )

        let data = try JSONEncoder().encode(state)
        let decoded = try JSONDecoder().decode(TaskActivityAttributes.ContentState.self, from: data)

        #expect(decoded.status == state.status)
        #expect(decoded.currentStep == state.currentStep)
        #expect(decoded.progress == state.progress)
        #expect(decoded.completedSteps == state.completedSteps)
        #expect(decoded.totalSteps == state.totalSteps)
        #expect(decoded.estimatedSecondsRemaining == state.estimatedSecondsRemaining)
        #expect(decoded.phaseIcon == state.phaseIcon)
    }

    @Test("ContentState APNs JSON payload'undan decode edilebilmeli")
    func contentState_fromAPNsPayload() throws {
        let apnsJSON = """
        {
            "status": "testing",
            "currentStep": "Tester is running suite...",
            "progress": 0.75,
            "completedSteps": 3,
            "totalSteps": 4,
            "estimatedSecondsRemaining": 60,
            "phaseIcon": "checkmark.circle"
        }
        """.data(using: .utf8)!

        let state = try JSONDecoder().decode(
            TaskActivityAttributes.ContentState.self,
            from: apnsJSON
        )

        #expect(state.status == "testing")
        #expect(state.currentStep == "Tester is running suite...")
        #expect(state.progress == 0.75)
        #expect(state.completedSteps == 3)
        #expect(state.totalSteps == 4)
        #expect(state.estimatedSecondsRemaining == 60)
        #expect(state.phaseIcon == "checkmark.circle")
    }

    @Test("ContentState tum alanlar mevcut olmali")
    func contentState_allFieldsPresent() {
        let state = TaskActivityAttributes.ContentState(
            status: "planning",
            currentStep: "Architect is analyzing...",
            progress: 0.1,
            completedSteps: 0,
            totalSteps: 6,
            estimatedSecondsRemaining: 300,
            phaseIcon: "brain.head.profile"
        )

        // Tum zorunlu alanlar mevcut ve dogru tipte
        #expect(!state.status.isEmpty)
        #expect(!state.currentStep.isEmpty)
        #expect(state.completedSteps >= 0)
        #expect(state.totalSteps > 0)
        #expect(state.estimatedSecondsRemaining != nil)
        #expect(!state.phaseIcon.isEmpty)
    }

    @Test("ContentState progress 0.0 ile 1.0 arasinda olmali")
    func contentState_progressRange() {
        let stateZero = TaskActivityAttributes.ContentState(
            status: "planning",
            currentStep: "Starting...",
            progress: 0.0,
            completedSteps: 0,
            totalSteps: 5,
            estimatedSecondsRemaining: nil,
            phaseIcon: "circle"
        )

        let stateOne = TaskActivityAttributes.ContentState(
            status: "completed",
            currentStep: "Done",
            progress: 1.0,
            completedSteps: 5,
            totalSteps: 5,
            estimatedSecondsRemaining: 0,
            phaseIcon: "checkmark.seal.fill"
        )

        #expect(stateZero.progress >= 0.0)
        #expect(stateZero.progress <= 1.0)
        #expect(stateOne.progress >= 0.0)
        #expect(stateOne.progress <= 1.0)
    }

    // MARK: - Static Attributes

    @Test("Attributes static alanlari dogru olmali")
    func attributes_staticFields() {
        let attributes = TaskActivityAttributes(
            taskId: "task-42",
            taskTitle: "Implement login flow",
            projectName: "RafRaf"
        )

        #expect(attributes.taskId == "task-42")
        #expect(attributes.taskTitle == "Implement login flow")
        #expect(attributes.projectName == "RafRaf")
    }

    @Test("Attributes encode → decode roundtrip basarili olmali")
    func attributes_codableRoundtrip() throws {
        let attributes = TaskActivityAttributes(
            taskId: "task-99",
            taskTitle: "Setup CI pipeline",
            projectName: "Backend Service"
        )

        let data = try JSONEncoder().encode(attributes)
        let decoded = try JSONDecoder().decode(TaskActivityAttributes.self, from: data)

        #expect(decoded.taskId == attributes.taskId)
        #expect(decoded.taskTitle == attributes.taskTitle)
        #expect(decoded.projectName == attributes.projectName)
    }
}
