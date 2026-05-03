import Foundation

/// V1.x SHIP BLOCKER fix — backend `ack` envelope handler'i.
///
/// Backend her critical client→server mesaj icin `type: "ack"` envelope yayinlar
/// (`shared/api-contracts/ws/ack-messages.json`); envelope `metadata.client_message_id`
/// ile gonderdigimiz id'yi echo'lar. Bu handler ack envelope'i alir, id'yi
/// `ApprovalDeliveryAckInbox`'a delege ederek bekleyen `awaitAck`
/// continuation'ini cozer.
///
/// Inbox uygulama icinde singleton — bu handler ve `ApprovalRepositoryImpl`
/// uretim path'i ayni instance'i paylasmali (DI: `Container.approvalDeliveryAckInbox`).
final class ApprovalDeliveryAckMessageHandler: WebSocketMessageHandler {
    private let inbox: ApprovalDeliveryAckInbox
    private let logger = AppLogger.logger(for: "ApprovalDeliveryAck")

    init(inbox: ApprovalDeliveryAckInbox) {
        self.inbox = inbox
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard let clientMessageId = message.metadata?.clientMessageId,
              !clientMessageId.isEmpty else {
            logger.warning("ack envelope client_message_id icermiyor: \(message.id, privacy: .public)")
            return
        }
        await inbox.handleAck(clientMessageId: clientMessageId)
        logger.debug("ack islendi clientMessageId=\(clientMessageId, privacy: .public)")
    }
}
