import Foundation

/// Mesaj yer imi servisi — UserDefaults ile yerel kalici depolama.
@Observable
@MainActor
final class BookmarkService: Sendable {
    private let userDefaultsKey = "chat.bookmarks"

    private(set) var bookmarks: [BookmarkedMessage] = []

    init() {
        load()
    }

    func bookmark(_ message: ChatMessage, projectId: String?, projectName: String?) {
        guard !isBookmarked(message.id) else { return }
        let bm = BookmarkedMessage(
            id: message.id,
            content: message.content,
            timestamp: message.timestamp,
            savedAt: Date(),
            projectId: projectId,
            projectName: projectName
        )
        bookmarks.insert(bm, at: 0)
        save()
    }

    func removeBookmark(id: String) {
        bookmarks.removeAll { $0.id == id }
        save()
    }

    func isBookmarked(_ id: String) -> Bool {
        bookmarks.contains { $0.id == id }
    }

    private func save() {
        if let data = try? JSONEncoder().encode(bookmarks) {
            UserDefaults.standard.set(data, forKey: userDefaultsKey)
        }
    }

    private func load() {
        guard let data = UserDefaults.standard.data(forKey: userDefaultsKey),
              let decoded = try? JSONDecoder().decode([BookmarkedMessage].self, from: data)
        else { return }
        bookmarks = decoded
    }
}

/// Yer imi kaydedilmis mesaj modeli.
struct BookmarkedMessage: Identifiable, Codable, Sendable {
    let id: String
    let content: String
    let timestamp: Date
    let savedAt: Date
    let projectId: String?
    let projectName: String?
}
