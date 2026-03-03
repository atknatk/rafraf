import Foundation
import Testing
@testable import RafRaf

/// ApprovalCardViewModel testleri.
@Suite("ApprovalCardViewModel Tests")
struct ApprovalCardViewModelTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT(
        repository: MockApprovalRepository = MockApprovalRepository()
    ) -> (ApprovalCardViewModel, MockApprovalRepository) {
        let vm = ApprovalCardViewModel(
            submitDecisionUseCase: SubmitApprovalDecisionUseCase(repository: repository)
        )
        return (vm, repository)
    }

    // MARK: - Initial State

    @Test("Baslangic durumu dogru olmali")
    @MainActor
    func initialState() {
        let (vm, _) = makeSUT()

        #expect(vm.question == nil)
        #expect(vm.remainingSeconds == 0)
        #expect(vm.isSubmitting == false)
        #expect(vm.isVisible == false)
        #expect(vm.isDecided == false)
        #expect(vm.errorMessage == nil)
    }

    // MARK: - Show Question

    @Test("showQuestion soruyu ve timer'i ayarlamali")
    @MainActor
    func showQuestion() {
        let (vm, _) = makeSUT()
        let question = ApprovalTestFactory.makeQuestion(timeoutSeconds: 30)

        vm.showQuestion(question)

        #expect(vm.question?.id == question.id)
        #expect(vm.remainingSeconds == 30)
        #expect(vm.isVisible == true)
        #expect(vm.isDecided == false)
        #expect(vm.isSubmitting == false)
        #expect(vm.errorMessage == nil)
    }

    @Test("showQuestion onceki soruyu degistirmeli")
    @MainActor
    func showQuestionReplacesExisting() {
        let (vm, _) = makeSUT()
        let firstQuestion = ApprovalTestFactory.makeQuestion(
            id: "first-123",
            timeoutSeconds: 60
        )
        let secondQuestion = ApprovalTestFactory.makeQuestion(
            id: "second-456",
            timeoutSeconds: 15
        )

        vm.showQuestion(firstQuestion)
        vm.showQuestion(secondQuestion)

        #expect(vm.question?.id == "second-456")
        #expect(vm.remainingSeconds == 15)
    }

    // MARK: - Progress Fraction

    @Test("progressFraction dogru hesaplanmali")
    @MainActor
    func progressFraction() {
        let (vm, _) = makeSUT()
        let question = ApprovalTestFactory.makeQuestion(timeoutSeconds: 100)

        vm.showQuestion(question)
        // remainingSeconds == 100, timeoutSeconds == 100
        #expect(vm.progressFraction == 1.0)
    }

    @Test("progressFraction soru yokken 0 olmali")
    @MainActor
    func progressFractionNoQuestion() {
        let (vm, _) = makeSUT()

        #expect(vm.progressFraction == 0.0)
    }

    // MARK: - Dangerous Category

    @Test("deploy kategorisi tehlikeli olmali")
    @MainActor
    func isDangerousDeploy() {
        let (vm, _) = makeSUT()
        let question = ApprovalTestFactory.makeQuestion(category: .deploy)

        vm.showQuestion(question)

        #expect(vm.isDangerousCategory == true)
    }

    @Test("destructive kategorisi tehlikeli olmali")
    @MainActor
    func isDangerousDestructive() {
        let (vm, _) = makeSUT()
        let question = ApprovalTestFactory.makeQuestion(category: .destructive)

        vm.showQuestion(question)

        #expect(vm.isDangerousCategory == true)
    }

    @Test("infrastructure kategorisi tehlikeli olmamali")
    @MainActor
    func isNotDangerousInfrastructure() {
        let (vm, _) = makeSUT()
        let question = ApprovalTestFactory.makeQuestion(category: .infrastructure)

        vm.showQuestion(question)

        #expect(vm.isDangerousCategory == false)
    }

    @Test("writeRemote kategorisi tehlikeli olmamali")
    @MainActor
    func isNotDangerousWriteRemote() {
        let (vm, _) = makeSUT()
        let question = ApprovalTestFactory.makeQuestion(category: .writeRemote)

        vm.showQuestion(question)

        #expect(vm.isDangerousCategory == false)
    }

    @Test("soru yokken isDangerousCategory false olmali")
    @MainActor
    func isDangerousNoQuestion() {
        let (vm, _) = makeSUT()

        #expect(vm.isDangerousCategory == false)
    }

    // MARK: - Submit Decision

    @Test("Basarili onay karari gondermeli")
    @MainActor
    func submitDecisionApproved() async {
        let (vm, repo) = makeSUT()
        let question = ApprovalTestFactory.makeQuestion()
        vm.showQuestion(question)

        await vm.submitDecision(optionId: "approve", decision: .approved)

        #expect(repo.submitDecisionCallCount == 1)
        #expect(repo.lastDecision == .approved)
        #expect(vm.isDecided == true)
        #expect(vm.isSubmitting == false)
    }

    @Test("Basarili red karari gondermeli")
    @MainActor
    func submitDecisionRejected() async {
        let (vm, repo) = makeSUT()
        let question = ApprovalTestFactory.makeQuestion()
        vm.showQuestion(question)

        await vm.submitDecision(optionId: "reject", decision: .rejected)

        #expect(repo.submitDecisionCallCount == 1)
        #expect(repo.lastDecision == .rejected)
        #expect(vm.isDecided == true)
    }

    @Test("Karar hatasinda hata mesaji gostermeli")
    @MainActor
    func submitDecisionError() async {
        let repo = MockApprovalRepository()
        repo.submitDecisionResult = .failure(ApprovalRepositoryError.sendFailed)
        let (vm, _) = makeSUT(repository: repo)
        let question = ApprovalTestFactory.makeQuestion()
        vm.showQuestion(question)

        await vm.submitDecision(optionId: "approve", decision: .approved)

        #expect(vm.errorMessage != nil)
        #expect(vm.isDecided == false)
        #expect(vm.isSubmitting == false)
    }

    @Test("Karar verilmis iken tekrar karar gondermemeli")
    @MainActor
    func submitDecisionAlreadyDecided() async {
        let (vm, repo) = makeSUT()
        let question = ApprovalTestFactory.makeQuestion()
        vm.showQuestion(question)

        // Ilk karar
        await vm.submitDecision(optionId: "approve", decision: .approved)
        #expect(repo.submitDecisionCallCount == 1)

        // Ikinci karar engellenmeli
        await vm.submitDecision(optionId: "reject", decision: .rejected)
        #expect(repo.submitDecisionCallCount == 1)
    }

    @Test("Soru yokken karar gondermemeli")
    @MainActor
    func submitDecisionNoQuestion() async {
        let (vm, repo) = makeSUT()

        await vm.submitDecision(optionId: "approve", decision: .approved)

        #expect(repo.submitDecisionCallCount == 0)
    }

    // MARK: - Dismiss

    @Test("dismiss karti gizlemeli")
    @MainActor
    func dismiss() {
        let (vm, _) = makeSUT()
        let question = ApprovalTestFactory.makeQuestion()
        vm.showQuestion(question)
        #expect(vm.isVisible == true)

        vm.dismiss()

        #expect(vm.isVisible == false)
    }
}
