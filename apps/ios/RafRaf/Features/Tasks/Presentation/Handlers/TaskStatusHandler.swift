import Foundation

/// WebSocket task_status mesajlarini isleyen handler.
final class TaskStatusHandler: WebSocketMessageHandler {
    private let onStatusUpdate: @Sendable (TaskStatusContent) -> Void

    init(onStatusUpdate: @escaping @Sendable (TaskStatusContent) -> Void) {
        self.onStatusUpdate = onStatusUpdate
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .taskStatus(let content) = message.content else { return }
        onStatusUpdate(content)
    }
}
