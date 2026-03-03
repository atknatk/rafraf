import Foundation
import Testing
@testable import RafRaf

/// ProgressMapper testleri.
@Suite("ProgressMapper Tests")
struct ProgressMapperTests {

    // MARK: - ProgressEventDTO -> ProgressState

    @Test("toDomain(ProgressEventDTO) determinate mod icin dogru donusturmeli")
    func mapEventDeterminate() {
        let dto = ProgressTestFactory.createProgressEvent(
            task: "Build gorevi",
            step: 3,
            totalSteps: 5,
            percentage: 60,
            details: "docker build"
        )

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.mode == .determinate)
        #expect(result.percentage == 60)
        #expect(result.taskDescription == "Build gorevi")
        #expect(result.steps.count == 5)
        #expect(result.currentStepIndex == 2) // step-1 (0-indexed)
        #expect(result.status == .running)
    }

    @Test("toDomain(ProgressEventDTO) indeterminate mod icin dogru donusturmeli")
    func mapEventIndeterminate() {
        let dto = ProgressTestFactory.createProgressEvent(
            task: "AI dusunuyor",
            step: 0,
            totalSteps: 0,
            percentage: 0
        )

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.mode == .indeterminate)
        #expect(result.steps.isEmpty)
        #expect(result.currentStepIndex == nil)
    }

    @Test("toDomain(ProgressEventDTO) tamamlanmis durumu dogru donusturmeli")
    func mapEventCompleted() {
        let dto = ProgressTestFactory.createProgressEvent(
            task: "Tamamlandi",
            step: 3,
            totalSteps: 3,
            percentage: 100
        )

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.status == .completed)
        #expect(result.percentage == 100)
    }

    @Test("toDomain(ProgressEventDTO) step durumlarini dogru ayarlamali")
    func mapEventStepStatuses() {
        let dto = ProgressTestFactory.createProgressEvent(
            step: 2,
            totalSteps: 4,
            percentage: 50
        )

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.steps.count == 4)
        #expect(result.steps[0].status == .completed)  // step 1 < current (2)
        #expect(result.steps[1].status == .active)      // step 2 == current
        #expect(result.steps[2].status == .pending)      // step 3 > current
        #expect(result.steps[3].status == .pending)      // step 4 > current
    }

    // MARK: - ProgressStateDTO -> ProgressState

    @Test("toDomain(ProgressStateDTO) tum alanlari dogru donusturmeli")
    func mapStateDTOComplete() {
        let stepDTOs = [
            ProgressTestFactory.createStepDTO(id: "s1", type: "thinking", status: "completed"),
            ProgressTestFactory.createStepDTO(id: "s2", type: "tool_calling", status: "active"),
        ]
        let dto = ProgressTestFactory.createProgressStateDTO(
            id: "state-1",
            mode: "determinate",
            percentage: 50,
            taskDescription: "Karmasik gorev",
            steps: stepDTOs,
            currentStepIndex: 1,
            status: "running"
        )

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.id == "state-1")
        #expect(result.mode == .determinate)
        #expect(result.percentage == 50)
        #expect(result.taskDescription == "Karmasik gorev")
        #expect(result.steps.count == 2)
        #expect(result.currentStepIndex == 1)
        #expect(result.status == .running)
    }

    @Test("toDomain(ProgressStateDTO) nil mode icin indeterminate olmali")
    func mapStateDTONilMode() {
        let dto = ProgressTestFactory.createProgressStateDTO(mode: nil)

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.mode == .indeterminate)
    }

    @Test("toDomain(ProgressStateDTO) nil status icin running olmali")
    func mapStateDTONilStatus() {
        let dto = ProgressTestFactory.createProgressStateDTO(status: nil)

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.status == .running)
    }

    @Test("toDomain(ProgressStateDTO) nil steps icin bos liste donmeli")
    func mapStateDTONilSteps() {
        let dto = ProgressTestFactory.createProgressStateDTO(steps: nil)

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.steps.isEmpty)
    }

    @Test("toDomain(ProgressStateDTO) bilinmeyen mode icin indeterminate donmeli")
    func mapStateDTOUnknownMode() {
        let dto = ProgressTestFactory.createProgressStateDTO(mode: "unknown_mode")

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.mode == .indeterminate)
    }

    @Test("toDomain(ProgressStateDTO) bilinmeyen status icin running donmeli")
    func mapStateDTOUnknownStatus() {
        let dto = ProgressTestFactory.createProgressStateDTO(status: "unknown_status")

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.status == .running)
    }

    // MARK: - ProgressStepDTO -> ProgressStep

    @Test("toDomain(ProgressStepDTO) tum alanlari dogru donusturmeli")
    func mapStepDTOComplete() {
        let dto = ProgressTestFactory.createStepDTO(
            id: "step-42",
            type: "tool_calling",
            label: "Docker build calisiyor",
            status: "active",
            durationSeconds: 5.2,
            detail: "docker build --tag app"
        )

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.id == "step-42")
        #expect(result.type == .toolCalling)
        #expect(result.label == "Docker build calisiyor")
        #expect(result.status == .active)
        #expect(result.durationSeconds == 5.2)
        #expect(result.detail == "docker build --tag app")
    }

    @Test("toDomain(ProgressStepDTO) bilinmeyen type icin thinking donmeli")
    func mapStepDTOUnknownType() {
        let dto = ProgressTestFactory.createStepDTO(type: "unknown_type")

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.type == .thinking)
    }

    @Test("toDomain(ProgressStepDTO) bilinmeyen status icin pending donmeli")
    func mapStepDTOUnknownStatus() {
        let dto = ProgressTestFactory.createStepDTO(status: "unknown_status")

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.status == .pending)
    }

    @Test("toDomain(ProgressStepDTO) nil optional alanlari nil olmali")
    func mapStepDTONilOptionals() {
        let dto = ProgressTestFactory.createStepDTO(durationSeconds: nil, detail: nil)

        let result = ProgressMapper.toDomain(from: dto)

        #expect(result.durationSeconds == nil)
        #expect(result.detail == nil)
    }
}
