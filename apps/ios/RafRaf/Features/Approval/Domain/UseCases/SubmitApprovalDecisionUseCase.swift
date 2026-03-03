import Foundation

/// Onay karari gonderme use case.
/// Kullanicinin onay/red kararini backend'e iletir.
struct SubmitApprovalDecisionUseCase: Sendable {
    private let repository: ApprovalRepositoryProtocol

    init(repository: ApprovalRepositoryProtocol) {
        self.repository = repository
    }

    /// Onay kararini gonderir.
    /// - Parameters:
    ///   - approvalId: Cevaplanan onay talebi ID'si
    ///   - decision: Kullanici karari
    ///   - note: Kullanici notu (opsiyonel)
    func execute(
        approvalId: String,
        decision: ApprovalDecision,
        note: String? = nil
    ) async throws {
        try await repository.submitDecision(
            approvalId: approvalId,
            decision: decision,
            note: note
        )
    }
}
