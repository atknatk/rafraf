import Foundation

/// `SessionTitleContent` (WebSocket DTO) → `SessionTitleUpdate` (domain) mapper.
///
/// Wire format: `apps/backend/app/schemas/messages.py::SessionTitlePayload`.
/// Doc 10 §6.4. T1.6 ile eklenen `SessionTitleContent` Sendable + Equatable
/// struct'ini domain `SessionTitleUpdate` value type'ina cevirir.
enum SessionTitleMapper {

    /// DTO'yu domain modeline donusturur.
    /// - Parameter content: Decode edilmis WebSocket payload.
    /// - Returns: Domain modeli.
    static func toDomain(_ content: SessionTitleContent) -> SessionTitleUpdate {
        SessionTitleUpdate(
            sessionId: content.sessionId,
            aiTitle: content.aiTitle,
            generatedAt: content.generatedAt
        )
    }
}
