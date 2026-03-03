import Foundation

/// Mesaj eki domain modeli.
struct ChatAttachment: Identifiable, Sendable, Equatable {
    let id: String
    let type: AttachmentType
    let url: String
    let mimeType: String
    let sizeBytes: Int

    init(
        id: String = UUID().uuidString,
        type: AttachmentType,
        url: String,
        mimeType: String,
        sizeBytes: Int
    ) {
        self.id = id
        self.type = type
        self.url = url
        self.mimeType = mimeType
        self.sizeBytes = sizeBytes
    }
}

/// Ek dosya tipi.
enum AttachmentType: String, Sendable, Equatable, CaseIterable {
    case image
    case file
    case audio
}
