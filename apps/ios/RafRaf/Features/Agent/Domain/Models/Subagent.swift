import Foundation

/// Bir Claude Agent Teams subagent calisma kaydi.
///
/// Bridge tarafindan emit edilen `subagent.spawned`, `subagent.progress` ve
/// `subagent.completed` WebSocket mesajlari bu modele projekte edilir.
/// `id` task_id'ye karsilik gelir; ayni id icin gelen sonraki guncellemeler
/// modeli yerinde gunceller (status / activity / ozet vs.).
///
/// Doc 10 §6.3.3 — iOS Agent feature subagent tree.
struct Subagent: Identifiable, Sendable, Hashable {
    /// Bridge `task_id` — subagent calismasinin benzersiz kimligi.
    let id: String

    /// Kullanici oturumu (ContentView WS metadata'si). Subagent'lar bu
    /// session altinda gruplanir.
    let sessionId: String

    /// Eger subagent baska bir subagent tarafindan spawn edildiyse o kaydin
    /// `id` degeri. `nil` ise top-level (ana session tarafindan spawn edilmis).
    /// T1.5/T1.6 payload'unda parent_task_id alani su anda yok; bu alan
    /// ileride bridge eklediginde eslenmek uzere model uzerinde tutulur ve
    /// agacin koklerinin bulunmasinda kullanilir.
    let parentTaskId: String?

    /// Subagent adi (ornek: "developer").
    let name: String

    /// Spawn'dan gelen serbest aciklama (Claude Code Task tool'undan).
    let description: String?

    /// `prompt`'in kisa onizlemesi — UI'da satira yerleshmesi icin.
    let promptPreview: String

    /// "general-purpose", "developer", "tester" gibi siniflandirma.
    let subagentType: String?

    /// "worktree" veya nil. Spec doc 10 §6.3.3'te isolation = "worktree" olan
    /// subagent'lar UI'da rozet ile vurgulanir.
    let isolation: String?

    /// Spawn -> in_progress -> completed/failed yasam dongusu.
    /// `var` cunku progress/completed event'leri bu degeri gunceller.
    var status: SubagentStatus

    /// Completed event'inden gelen ozet metni.
    var summary: String?

    /// Toplam token kullanimi (input + output). `Int?` cunku spawn aninda
    /// henuz bilinmez.
    var totalTokens: Int?

    /// Kac tool cagrisi yapildigi (tool_uses).
    var toolUses: Int?

    /// Subagent calisma suresi (ms). Completed payload'undan gelir.
    var durationMs: Int?

    /// Progress event'inden gelen aktivite mesaji (ornek: "running tests").
    var activity: String?

    /// `subagent.spawned` event'inin `started_at` zamani.
    let spawnedAt: Date

    /// Son progress/completed event'inin zamani.
    var updatedAt: Date?

    /// `subagent.completed` event'inin `completed_at` zamani.
    var completedAt: Date?
}

/// Bir subagent'in yasam dongusu durumu.
///
/// Bridge string degerleri: "spawned" | "in_progress" | "completed" | "failed".
/// Spawned bridge tarafindan yayilmaz — UI ilk kez gordugunde bu durumdadir.
enum SubagentStatus: String, Sendable, CaseIterable, Hashable {
    case spawned
    case inProgress = "in_progress"
    case completed
    case failed

    /// Bilinmeyen / future bir status string'ini en yakin bilinen duruma
    /// dusurur. Bridge yeni bir status eklerse UI bozulmaz.
    static func from(rawString raw: String) -> SubagentStatus {
        if let exact = SubagentStatus(rawValue: raw) {
            return exact
        }
        // Yedek: "running" / "active" gibi alternatif isimleri in_progress kabul et.
        switch raw.lowercased() {
        case "running", "active", "started":
            return .inProgress
        case "done", "success", "ok":
            return .completed
        case "error":
            return .failed
        default:
            return .inProgress
        }
    }
}
