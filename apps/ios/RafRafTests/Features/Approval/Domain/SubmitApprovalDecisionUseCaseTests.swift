import Foundation
import Testing
@testable import RafRaf

/// SubmitApprovalDecisionUseCase testleri.
@Suite("SubmitApprovalDecisionUseCase Tests")
struct SubmitApprovalDecisionUseCaseTests {

    // MARK: - Helpers

    private func makeSUT(
        repository: MockApprovalRepository = MockApprovalRepository()
    ) -> (SubmitApprovalDecisionUseCase, MockApprovalRepository) {
        let useCase = SubmitApprovalDecisionUseCase(repository: repository)
        return (useCase, repository)
    }

    // MARK: - Success

    @Test("Basarili approval karari gondermeli")
    func executeApproved() async throws {
        let (useCase, repo) = makeSUT()

        try await useCase.execute(
            approvalId: "test-123",
            decision: .approved
        )

        #expect(repo.submitDecisionCallCount == 1)
        #expect(repo.lastApprovalId == "test-123")
        #expect(repo.lastDecision == .approved)
        #expect(repo.lastNote == nil)
    }

    @Test("Basarili rejection karari note ile gondermeli")
    func executeRejectedWithNote() async throws {
        let (useCase, repo) = makeSUT()

        try await useCase.execute(
            approvalId: "test-456",
            decision: .rejected,
            note: "Timeout - otomatik red"
        )

        #expect(repo.submitDecisionCallCount == 1)
        #expect(repo.lastApprovalId == "test-456")
        #expect(repo.lastDecision == .rejected)
        #expect(repo.lastNote == "Timeout - otomatik red")
    }

    // MARK: - Error

    @Test("Repository hatasi durumunda hata firlatmali")
    func executeThrowsOnError() async {
        let repo = MockApprovalRepository()
        repo.submitDecisionResult = .failure(ApprovalRepositoryError.encodingFailed)
        let (useCase, _) = makeSUT(repository: repo)

        await #expect(throws: ApprovalRepositoryError.self) {
            try await useCase.execute(
                approvalId: "test-789",
                decision: .approved
            )
        }
    }
}
