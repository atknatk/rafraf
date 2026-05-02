import Foundation

/// Onay cevabi WebSocket mesaj DTO.
/// `shared/api-contracts/ws/approval-messages.json` kontratina uygun.
struct ApprovalResponseDTO: Codable, Sendable, Equatable {
    /// Cevaplanan onay talebi ID'si.
    let approvalId: String
    /// Kullanici karari (approved/rejected).
    let decision: String
    /// Kullanici notu (opsiyonel).
    let note: String?

    // Explicit snake_case CodingKeys: `WebSocketMessageRouter.encoder` does NOT apply
    // `convertToSnakeCase` (it would also rewrite handler-specific keys), so the DTO
    // owns its wire-key contract here. Backend `_handle_approval_response`
    // (apps/backend/app/api/routes/websocket.py:1049) reads exactly these snake_case
    // keys from the `content` dict.
    enum CodingKeys: String, CodingKey {
        case approvalId = "approval_id"
        case decision
        case note
    }
}
