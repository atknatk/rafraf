import Foundation

/// Bir session icin AI tarafindan uretilen yeni bir baslik bildirimi.
///
/// `session.title` WebSocket olayinin domain karsiligidir. Mac bridge
/// `~/.claude/projects/<proj>/<session>.jsonl` icindeki `ai-title` event'ini
/// algilayinca backend tarafindan tum baglii istemcilere yayinlanir.
///
/// Kontrat: `apps/backend/app/schemas/messages.py::SessionTitlePayload`.
/// Doc 10 §6.3.4.
struct SessionTitleUpdate: Sendable, Equatable, Identifiable {
    /// Backend session UUID stringi (doc 10 §6.4'te `UUID` ama wire format string).
    let sessionId: String

    /// Claude tarafindan uretilen yeni kisa baslik.
    let aiTitle: String

    /// Baslik uretim zamani (UTC).
    let generatedAt: Date

    /// `Identifiable` icin sessionId kullanilir.
    var id: String { sessionId }

    init(sessionId: String, aiTitle: String, generatedAt: Date) {
        self.sessionId = sessionId
        self.aiTitle = aiTitle
        self.generatedAt = generatedAt
    }
}
