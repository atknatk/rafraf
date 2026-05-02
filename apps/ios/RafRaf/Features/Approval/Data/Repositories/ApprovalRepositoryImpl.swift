import Foundation
import os

/// Onay repository implementasyonu.
/// WebSocket uzerinden onay kararlarini backend'e gonderir.
final class ApprovalRepositoryImpl: ApprovalRepositoryProtocol, @unchecked Sendable {
    private let webSocketClient: WebSocketClient
    private let messageRouter: WebSocketMessageRouter
    private let logger = AppLogger.logger(for: "Approval")

    init(
        webSocketClient: WebSocketClient,
        messageRouter: WebSocketMessageRouter
    ) {
        self.webSocketClient = webSocketClient
        self.messageRouter = messageRouter
    }

    func submitDecision(
        approvalId: String,
        decision: ApprovalDecision,
        note: String?
    ) async throws {
        let responseDTO = ApprovalMapper.toResponseDTO(
            approvalId: approvalId,
            decision: decision,
            note: note
        )

        // V1 SHIP fix: DTO'yu `.approvalResponse` case'i ile sariyoruz; bu sayede wire
        // formati `content: { "approval_id": ..., "decision": ..., "note": ... }` (dict)
        // olarak cikar. Eski yol DTO'yu JSON-string'e cevirip `.text(...)` icine
        // sariyordu; backend `_handle_approval_response` content'in dict olmasini
        // sart kosuyor (isinstance kontrolu) — uyumsuzluk timeout/auto-deny ile
        // sonuclanip kullanicinin "Allow once" tap'ini kaybediyordu.
        let message = WebSocketBaseMessage(
            type: "approval_response",
            content: .approvalResponse(responseDTO),
            metadata: WebSocketMessageMetadata(
                direction: WebSocketMessageDirection.clientToServer.rawValue
            )
        )

        let jsonString = try await messageRouter.encode(message)
        try await webSocketClient.send(jsonString)
        logger.info("Approval karari gonderildi: \(approvalId) -> \(decision.rawValue)")
    }
}

/// Approval repository hatalari.
enum ApprovalRepositoryError: Error, Sendable {
    case encodingFailed
    case sendFailed
}
