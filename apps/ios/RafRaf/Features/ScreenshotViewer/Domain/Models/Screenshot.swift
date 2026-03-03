import Foundation

/// Ekran goruntusu domain modeli.
struct Screenshot: Identifiable, Sendable, Equatable {
    let id: String
    let url: String
    let title: String?
    let timestamp: Date
    let width: Int?
    let height: Int?

    init(
        id: String = UUID().uuidString,
        url: String,
        title: String? = nil,
        timestamp: Date = Date(),
        width: Int? = nil,
        height: Int? = nil
    ) {
        self.id = id
        self.url = url
        self.title = title
        self.timestamp = timestamp
        self.width = width
        self.height = height
    }
}
