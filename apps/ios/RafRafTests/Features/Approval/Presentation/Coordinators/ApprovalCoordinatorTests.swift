import Foundation
import Testing
@testable import RafRaf

/// V1.5: ApprovalCoordinator queue + decision dispatch testleri.
@Suite("ApprovalCoordinator Tests")
struct ApprovalCoordinatorTests {

    // MARK: - Queue/Presentation

    @Test("enqueue bos durumda activeRequest set eder")
    @MainActor
    func enqueue_emptyQueue_setsActiveRequest() {
        let coordinator = makeCoordinator().coordinator
        let question = ApprovalTestFactory.makeQuestion(id: "q1", category: .destructive)

        coordinator.enqueue(question: question)

        #expect(coordinator.activeRequest != nil)
        #expect(coordinator.activeRequest?.id == "q1")
        #expect(coordinator.queue.isEmpty)
    }

    @Test("enqueue x3 — ilk aktif, sonraki 2 kuyrukta")
    @MainActor
    func enqueue_threeQuestions_oneActiveTwoQueued() {
        let coordinator = makeCoordinator().coordinator

        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "q1", category: .destructive))
        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "q2", category: .deploy))
        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "q3", category: .infrastructure))

        #expect(coordinator.activeRequest?.id == "q1")
        #expect(coordinator.queue.count == 2)
        #expect(coordinator.queue[0].id == "q2")
        #expect(coordinator.queue[1].id == "q3")
    }

    @Test("handleDecision aktif request'i temizler ve sonrakini sunar")
    @MainActor
    func handleDecision_dequeuesAndPresentsNext() async {
        let setup = makeCoordinator()
        let coordinator = setup.coordinator

        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "q1", category: .destructive))
        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "q2", category: .deploy))
        #expect(coordinator.activeRequest?.id == "q1")

        await coordinator.handleDecision(.allowOnce)

        // q1 gitti, q2 aktif, kuyruk bos.
        #expect(coordinator.activeRequest?.id == "q2")
        #expect(coordinator.queue.isEmpty)
    }

    @Test("handleDecision son request sonrasi activeRequest nil")
    @MainActor
    func handleDecision_lastRequest_clearsActive() async {
        let setup = makeCoordinator()
        let coordinator = setup.coordinator
        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "only", category: .destructive))

        await coordinator.handleDecision(.allowOnce)

        #expect(coordinator.activeRequest == nil)
        #expect(coordinator.queue.isEmpty)
    }

    @Test("handleDecision aktif request yokken no-op (use case cagrilmaz)")
    @MainActor
    func handleDecision_withoutActive_isNoop() async {
        let setup = makeCoordinator()
        let coordinator = setup.coordinator

        await coordinator.handleDecision(.allowOnce)

        #expect(setup.repository.submitDecisionCallCount == 0)
        #expect(coordinator.activeRequest == nil)
    }

    // MARK: - Decision Wire Mapping (allow_once / allow_session / deny)

    @Test("allowOnce -> approved + note nil")
    @MainActor
    func decision_allowOnce_mapsToApprovedWithoutNote() async {
        let setup = makeCoordinator()
        let coordinator = setup.coordinator
        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "appr-1"))

        await coordinator.handleDecision(.allowOnce)

        #expect(setup.repository.submitDecisionCallCount == 1)
        #expect(setup.repository.lastApprovalId == "appr-1")
        #expect(setup.repository.lastDecision == .approved)
        #expect(setup.repository.lastNote == nil)
    }

    @Test("allowSession -> approved + note 'allow_session' (V1 future-Faz4 hook)")
    @MainActor
    func decision_allowSession_mapsToApprovedWithSessionNote() async {
        let setup = makeCoordinator()
        let coordinator = setup.coordinator
        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "appr-2"))

        await coordinator.handleDecision(.allowSession)

        #expect(setup.repository.lastApprovalId == "appr-2")
        #expect(setup.repository.lastDecision == .approved)
        #expect(setup.repository.lastNote == "allow_session")
    }

    @Test("deny -> rejected on the wire (timeout/auto-deny da bu yolu kullanir)")
    @MainActor
    func decision_deny_mapsToRejected() async {
        let setup = makeCoordinator()
        let coordinator = setup.coordinator
        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "appr-3"))

        await coordinator.handleDecision(.deny)

        #expect(setup.repository.lastApprovalId == "appr-3")
        #expect(setup.repository.lastDecision == .rejected)
        #expect(setup.repository.lastNote == nil)
    }

    // MARK: - Failure Resilience

    @Test("submitDecision hata atsa bile sonraki sheet sunulur (fail-open queue)")
    @MainActor
    func decision_submitFailure_continuesQueue() async {
        let setup = makeCoordinator()
        setup.repository.submitDecisionResult = .failure(MockError.simulated)
        let coordinator = setup.coordinator

        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "fail", category: .destructive))
        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "next", category: .deploy))

        await coordinator.handleDecision(.deny)

        // Hata olmasi sonraki sheet'i bloklamamali — UI takilmaz, queue ilerler.
        #expect(coordinator.activeRequest?.id == "next")
    }

    // MARK: - Reset

    @Test("reset queue + activeRequest temizler")
    @MainActor
    func reset_clearsState() {
        let coordinator = makeCoordinator().coordinator
        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "x"))
        coordinator.enqueue(question: ApprovalTestFactory.makeQuestion(id: "y"))

        coordinator.reset()

        #expect(coordinator.activeRequest == nil)
        #expect(coordinator.queue.isEmpty)
    }

    // MARK: - Helpers

    @MainActor
    private func makeCoordinator() -> (coordinator: ApprovalCoordinator, repository: MockApprovalRepository) {
        let repository = MockApprovalRepository()
        let useCase = SubmitApprovalDecisionUseCase(repository: repository)
        let coordinator = ApprovalCoordinator(submitDecisionUseCase: useCase)
        return (coordinator, repository)
    }
}

private enum MockError: Error {
    case simulated
}
