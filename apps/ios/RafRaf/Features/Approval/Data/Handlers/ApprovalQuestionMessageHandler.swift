import Foundation

/// V1.5: Backend `question` envelope -> ApprovalCoordinator handler.
///
/// `WebSocketMessageRouter`'a `WebSocketMessageType.question.rawValue`
/// type'i icin kaydedilir (ContentView.task icinde bir kez). Decode edilen
/// `WebSocketContent.question(ApprovalQuestionDTO)` payload'u ApprovalQuestion
/// domain modeline donusturulup coordinator'in kuyruguna eklenir.
///
/// Coordinator @MainActor — handler.handle nonisolated context'tan cagrilabilir
/// (router actor'i), bu yuzden coordinator dispatch'ini @MainActor'a hop ediyoruz.
final class ApprovalQuestionMessageHandler: WebSocketMessageHandler {
    private let coordinator: ApprovalCoordinator
    private let logger = AppLogger.logger(for: "ApprovalQuestionHandler")

    init(coordinator: ApprovalCoordinator) {
        self.coordinator = coordinator
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .question(let dto) = message.content else {
            logger.warning("question content beklenen tipte degil: \(message.id)")
            return
        }
        let question = ApprovalMapper.toQuestion(dto: dto)
        await MainActor.run {
            coordinator.enqueue(question: question)
        }
    }
}
