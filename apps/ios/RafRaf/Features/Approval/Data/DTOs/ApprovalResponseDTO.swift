import Foundation

/// Onay cevabi WebSocket mesaj DTO.
/// `shared/api-contracts/ws/approval-messages.json` kontratina uygun.
struct ApprovalResponseDTO: Codable, Sendable {
    /// Cevaplanan onay talebi ID'si.
    let approvalId: String
    /// Kullanici karari (approved/rejected).
    let decision: String
    /// Kullanici notu (opsiyonel).
    let note: String?
}
