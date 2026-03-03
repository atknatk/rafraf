import Foundation
import Testing
@testable import RafRaf

/// ProgressViewModel testleri.
@Suite("ProgressViewModel Tests")
struct ProgressViewModelTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT(
        repository: MockProgressRepository = MockProgressRepository()
    ) -> (ProgressViewModel, MockProgressRepository) {
        let useCase = ObserveProgressUseCase(repository: repository)
        let vm = ProgressViewModel(observeProgressUseCase: useCase)
        return (vm, repository)
    }

    // MARK: - Initial State

    @Test("ProgressViewModel baslangic durumu dogru olmali")
    @MainActor
    func initialState() {
        let (vm, _) = makeSUT()

        #expect(vm.progressState == nil)
        #expect(vm.isVisible == false)
        #expect(vm.errorMessage == nil)
        #expect(vm.isActive == false)
        #expect(vm.progressFraction == 0.0)
        #expect(vm.currentStep == nil)
        #expect(vm.isDeterminate == false)
        #expect(vm.completedStepCount == 0)
        #expect(vm.totalStepCount == 0)
        #expect(vm.taskDescription == "")
    }

    // MARK: - Update Progress

    @Test("updateProgress state ve visibility guncellemeli")
    @MainActor
    func updateProgress() {
        let (vm, _) = makeSUT()
        let state = ProgressTestFactory.createState(
            percentage: 50,
            taskDescription: "Test gorevi",
            status: .running
        )

        vm.updateProgress(state)

        #expect(vm.progressState != nil)
        #expect(vm.isVisible == true)
        #expect(vm.taskDescription == "Test gorevi")
        #expect(vm.progressFraction == 0.5)
    }

    @Test("updateProgress determinate modda computed degerleri dogru olmali")
    @MainActor
    func updateProgressDeterminate() {
        let (vm, _) = makeSUT()
        let state = ProgressTestFactory.createThreeStepState()

        vm.updateProgress(state)

        #expect(vm.isDeterminate == true)
        #expect(vm.totalStepCount == 3)
        #expect(vm.completedStepCount == 1)
        #expect(vm.currentStep?.type == .toolCalling)
    }

    @Test("updateProgress indeterminate modda isDeterminate false olmali")
    @MainActor
    func updateProgressIndeterminate() {
        let (vm, _) = makeSUT()
        let state = ProgressTestFactory.createState(
            mode: .indeterminate,
            taskDescription: "AI dusunuyor"
        )

        vm.updateProgress(state)

        #expect(vm.isDeterminate == false)
        #expect(vm.isActive == true)
    }

    @Test("updateProgress completed durumda isActive false olmali")
    @MainActor
    func updateProgressCompleted() {
        let (vm, _) = makeSUT()
        let state = ProgressTestFactory.createState(
            percentage: 100,
            taskDescription: "Tamamlandi",
            status: .completed
        )

        vm.updateProgress(state)

        #expect(vm.isActive == false)
        #expect(vm.progressFraction == 1.0)
    }

    // MARK: - Update From Event

    @Test("updateFromEvent determinate event'i state'e donusturmeli")
    @MainActor
    func updateFromEventDeterminate() {
        let (vm, _) = makeSUT()

        vm.updateFromEvent(
            task: "Build calisiyor",
            step: 2,
            totalSteps: 4,
            percentage: 50,
            details: "Step 2 detail"
        )

        #expect(vm.progressState != nil)
        #expect(vm.isDeterminate == true)
        #expect(vm.totalStepCount == 4)
        #expect(vm.progressFraction == 0.5)
        #expect(vm.taskDescription == "Build calisiyor")
        #expect(vm.isVisible == true)
    }

    @Test("updateFromEvent indeterminate event'i state'e donusturmeli")
    @MainActor
    func updateFromEventIndeterminate() {
        let (vm, _) = makeSUT()

        vm.updateFromEvent(
            task: "Analiz ediliyor",
            step: 0,
            totalSteps: 0,
            percentage: 0,
            details: nil
        )

        #expect(vm.isDeterminate == false)
        #expect(vm.totalStepCount == 0)
        #expect(vm.isActive == true)
    }

    @Test("updateFromEvent tamamlanan event icin completed olmali")
    @MainActor
    func updateFromEventCompleted() {
        let (vm, _) = makeSUT()

        vm.updateFromEvent(
            task: "Tamamlandi",
            step: 3,
            totalSteps: 3,
            percentage: 100,
            details: nil
        )

        #expect(vm.progressState?.status == .completed)
        #expect(vm.isActive == false)
    }

    @Test("updateFromEvent step durumlarini dogru ayarlamali")
    @MainActor
    func updateFromEventStepStatuses() {
        let (vm, _) = makeSUT()

        vm.updateFromEvent(
            task: "Test",
            step: 2,
            totalSteps: 3,
            percentage: 66,
            details: nil
        )

        let steps = vm.progressState?.steps ?? []
        #expect(steps.count == 3)
        #expect(steps[0].status == .completed)
        #expect(steps[1].status == .active)
        #expect(steps[2].status == .pending)
    }

    // MARK: - Update Tool Status

    @Test("updateToolStatus aktif step'in detayini guncellemeli")
    @MainActor
    func updateToolStatus() {
        let (vm, _) = makeSUT()
        let state = ProgressTestFactory.createThreeStepState()
        vm.updateProgress(state)

        vm.updateToolStatus(toolName: "playwright", action: "navigate", isRunning: true)

        let activeStep = vm.progressState?.steps.first { $0.status == .active }
        #expect(activeStep?.detail == "playwright: navigate")
        #expect(activeStep?.type == .toolCalling)
    }

    @Test("updateToolStatus state olmadigi durumda islem yapmamali")
    @MainActor
    func updateToolStatusNoState() {
        let (vm, _) = makeSUT()

        // Hata atmamalI
        vm.updateToolStatus(toolName: "docker", action: "build", isRunning: true)

        #expect(vm.progressState == nil)
    }

    // MARK: - Mark Completed

    @Test("markCompleted tum step'leri completed yapmali")
    @MainActor
    func markCompleted() {
        let (vm, _) = makeSUT()
        let state = ProgressTestFactory.createThreeStepState()
        vm.updateProgress(state)

        vm.markCompleted()

        #expect(vm.progressState?.status == .completed)
        #expect(vm.progressState?.percentage == 100)

        let allCompleted = vm.progressState?.steps.allSatisfy { $0.status == .completed } ?? false
        #expect(allCompleted)
    }

    @Test("markCompleted state olmadigi durumda islem yapmamali")
    @MainActor
    func markCompletedNoState() {
        let (vm, _) = makeSUT()

        // Hata atmamalI
        vm.markCompleted()

        #expect(vm.progressState == nil)
    }

    // MARK: - Mark Failed

    @Test("markFailed hata durumunu ayarlamali")
    @MainActor
    func markFailed() {
        let (vm, _) = makeSUT()
        let state = ProgressTestFactory.createState()
        vm.updateProgress(state)

        vm.markFailed(error: "Build hatasi")

        #expect(vm.progressState?.status == .failed)
        #expect(vm.errorMessage == "Build hatasi")
    }

    @Test("markFailed state olmadigi durumda sadece error ayarlamali")
    @MainActor
    func markFailedNoState() {
        let (vm, _) = makeSUT()

        vm.markFailed(error: "Hata")

        #expect(vm.progressState == nil)
        #expect(vm.errorMessage == "Hata")
    }

    // MARK: - Dismiss

    @Test("dismiss visibility'yi false yapmali")
    @MainActor
    func dismiss() {
        let (vm, _) = makeSUT()
        let state = ProgressTestFactory.createState()
        vm.updateProgress(state)
        #expect(vm.isVisible == true)

        vm.dismiss()

        #expect(vm.isVisible == false)
    }

    // MARK: - Dismiss Error

    @Test("dismissError hata mesajini temizlemeli")
    @MainActor
    func dismissError() {
        let (vm, _) = makeSUT()
        vm.markFailed(error: "Test hatasi")
        #expect(vm.errorMessage != nil)

        vm.dismissError()

        #expect(vm.errorMessage == nil)
    }

    // MARK: - Computed Properties

    @Test("progressFraction state olmadigi durumda 0 donmeli")
    @MainActor
    func progressFractionNoState() {
        let (vm, _) = makeSUT()
        #expect(vm.progressFraction == 0.0)
    }

    @Test("progressFraction yuzde 100 icin 1.0 donmeli")
    @MainActor
    func progressFractionFull() {
        let (vm, _) = makeSUT()
        let state = ProgressTestFactory.createState(percentage: 100)
        vm.updateProgress(state)
        #expect(vm.progressFraction == 1.0)
    }

    @Test("currentStep gecersiz index icin nil donmeli")
    @MainActor
    func currentStepInvalidIndex() {
        let (vm, _) = makeSUT()
        let state = ProgressTestFactory.createState(
            steps: [ProgressTestFactory.createStep()],
            currentStepIndex: 5 // Out of bounds
        )
        vm.updateProgress(state)
        #expect(vm.currentStep == nil)
    }

    @Test("currentStep negatif index icin nil donmeli")
    @MainActor
    func currentStepNegativeIndex() {
        let (vm, _) = makeSUT()
        let state = ProgressTestFactory.createState(
            steps: [ProgressTestFactory.createStep()],
            currentStepIndex: -1
        )
        vm.updateProgress(state)
        #expect(vm.currentStep == nil)
    }

    @Test("taskDescription state olmadigi durumda bos string donmeli")
    @MainActor
    func taskDescriptionNoState() {
        let (vm, _) = makeSUT()
        #expect(vm.taskDescription == "")
    }
}
