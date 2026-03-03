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

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let payloadData = try encoder.encode(responseDTO)

        guard let payloadString = String(data: payloadData, encoding: .utf8) else {
            logger.error("Approval response encode edilemedi")
            throw ApprovalRepositoryError.encodingFailed
        }

        let message = WebSocketBaseMessage(
            type: "approval_response",
            content: .text(payloadString),
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
