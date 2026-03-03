import Foundation

/// Onay islemleri repository protokolu.
/// Data katmanindaki WebSocket iletisimini soyutlar.
protocol ApprovalRepositoryProtocol: Sendable {
    /// Onay kararini backend'e gonderir.
    /// - Parameters:
    ///   - approvalId: Cevaplanan onay talebi ID'si
    ///   - decision: Kullanici karari (approved/rejected)
    ///   - note: Kullanici notu (opsiyonel)
    func submitDecision(
        approvalId: String,
        decision: ApprovalDecision,
        note: String?
    ) async throws
}
