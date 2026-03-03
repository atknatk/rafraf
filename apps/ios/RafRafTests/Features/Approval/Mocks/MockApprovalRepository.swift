import Foundation
@testable import RafRaf

/// Test icin mock approval repository.
final class MockApprovalRepository: ApprovalRepositoryProtocol, @unchecked Sendable {
    var submitDecisionResult: Result<Void, Error> = .success(())
    var submitDecisionCallCount = 0
    var lastApprovalId: String?
    var lastDecision: ApprovalDecision?
    var lastNote: String?

    func submitDecision(
        approvalId: String,
        decision: ApprovalDecision,
        note: String?
    ) async throws {
        submitDecisionCallCount += 1
        lastApprovalId = approvalId
        lastDecision = decision
        lastNote = note
        try submitDecisionResult.get()
    }
}
