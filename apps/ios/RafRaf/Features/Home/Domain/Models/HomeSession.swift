import Foundation

/// Home ekraninda gosterilen sohbet oturumu (session) ozeti.
///
/// Bir oturum bir Claude session'ina karsilik gelir. `title` raw fallback
/// (orn. session_id veya kullanicinin ilk mesaji) iken `aiTitle` Claude
/// tarafindan storage watcher (Mac bridge `~/.claude/projects/`) uzerinden
/// uretilen anlamli baslik. Mevcut oldugunda `aiTitle` UI'da one cikar.
///
/// Doc 10 §6.3.4 — "session listesindeki başlık alanı raw session_id veya
/// kullanıcının ilk mesajı yerine, varsa `session.title` (storage'dan gelen
/// `ai-title`)".
struct HomeSession: Identifiable, Sendable, Equatable {
    /// Backend session UUID stringi.
    let id: String

    /// Fallback baslik (kullanicinin ilk mesaji veya session_id).
    let title: String

    /// Claude tarafindan uretilmis kisa baslik. nil ise henuz uretilmemis.
    let aiTitle: String?

    /// Son aktivite zamani.
    let lastActivity: Date

    /// AI baslik mevcut ise onu, degilse fallback'i dondurur.
    var displayTitle: String {
        aiTitle ?? title
    }

    /// AI tarafindan uretilmis bir baslik var mi?
    var hasAITitle: Bool {
        aiTitle?.isEmpty == false
    }

    init(
        id: String,
        title: String,
        aiTitle: String? = nil,
        lastActivity: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.aiTitle = aiTitle
        self.lastActivity = lastActivity
    }

    /// Yeni AI baslik ile guncellenmis kopya dondurur.
    func updatingAITitle(_ newTitle: String) -> HomeSession {
        HomeSession(
            id: id,
            title: title,
            aiTitle: newTitle,
            lastActivity: lastActivity
        )
    }
}
