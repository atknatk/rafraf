import Foundation
import os

/// Locally persisted message queue for offline support.
/// Messages queued while disconnected are sent automatically on reconnect.
@Observable @MainActor final class MessageQueue {
    private let logger = Logger(subsystem: "com.atknatk.rafraf", category: "MessageQueue")
    private let defaults = UserDefaults.standard
    private let key = "rafraf.message_queue"

    private(set) var pendingMessages: [QueuedMessage] = []

    struct QueuedMessage: Identifiable, Codable, Sendable {
        let id: String
        let text: String
        let projectId: String?
        let agentId: String?
        let queuedAt: Date

        init(text: String, projectId: String? = nil, agentId: String? = nil) {
            self.id = UUID().uuidString
            self.text = text
            self.projectId = projectId
            self.agentId = agentId
            self.queuedAt = Date()
        }
    }

    init() {
        loadFromDisk()
    }

    func enqueue(text: String, projectId: String? = nil, agentId: String? = nil) {
        let msg = QueuedMessage(text: text, projectId: projectId, agentId: agentId)
        pendingMessages.append(msg)
        saveToDisk()
        logger.info("Message queued offline: \(msg.id)")
    }

    func dequeue(_ id: String) {
        pendingMessages.removeAll { $0.id == id }
        saveToDisk()
    }

    func dequeueAll() -> [QueuedMessage] {
        let all = pendingMessages
        pendingMessages = []
        saveToDisk()
        return all
    }

    var isEmpty: Bool { pendingMessages.isEmpty }
    var count: Int { pendingMessages.count }

    private func saveToDisk() {
        guard let data = try? JSONEncoder().encode(pendingMessages) else { return }
        defaults.set(data, forKey: key)
    }

    private func loadFromDisk() {
        guard let data = defaults.data(forKey: key),
              let messages = try? JSONDecoder().decode([QueuedMessage].self, from: data)
        else { return }
        pendingMessages = messages
    }
}
