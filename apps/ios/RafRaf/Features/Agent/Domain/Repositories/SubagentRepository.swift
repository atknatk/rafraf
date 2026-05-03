import Foundation

/// Subagent state repository protokolu.
///
/// Doc 10 §6.3.3 — bridge'in yayinladigi `subagent.spawned`,
/// `subagent.progress`, `subagent.completed` mesajlari Data katmanindaki
/// mapper'larla Domain modeline (Subagent / SubagentUpdate) cevrilir ve bu
/// repository uzerinden UI'a stream olarak yayilir.
///
/// Domain katmani Data/Network tiplerine bagli kalmaz — `SubagentUpdate`
/// salt domain bir tiptir. Boylece test edilebilirlik korunur ve Clean
/// Architecture izolasyon kurali ihlal edilmez.
protocol SubagentRepository: Sendable {

    /// Belirli bir session icin subagent listesini stream olarak yayilir.
    ///
    /// Stream subscribe oldugunda mevcut snapshot'i ilk eleman olarak
    /// yayar; ardindan her degisiklikte (spawn / progress / complete) tum
    /// guncel listeyi `spawnedAt` artan sirada yeniden yayinlar.
    func observeSubagents(sessionId: String) async -> AsyncStream<[Subagent]>

    /// Tum oturumlardaki subagent'larin birlestirilmis stream'i.
    /// AgentDetailView gibi yer-bagimsiz goruntulemelerde kullanilir.
    /// `spawnedAt` artan sirada yayilir.
    func observeAllSubagents() async -> AsyncStream<[Subagent]>

    /// Mevcut anlik subagent listesini dondurur — `spawnedAt` artan sirada.
    func currentSubagents(sessionId: String) async -> [Subagent]

    /// Tum oturumlardan birlestirilmis anlik snapshot.
    func currentAllSubagents() async -> [Subagent]

    /// Domain seviyesinde olusturulmus bir guncellemeyi state'e uygula.
    /// Spawn -> ekle (varsa replace), progress/completed -> mevcut kaydi
    /// in-place gunceller (yoksa kaydi yaratamayacagi icin gormezden gelir).
    func apply(update: SubagentUpdate) async

    /// Bir session'a ait tum subagent kayitlarini temizle (logout / oturum
    /// kapanisi).
    func clear(sessionId: String) async

    /// Item 9 — Cold-start sonrasi backend'in son bilinen subagent state'ini
    /// REST uzerinden cek ve in-memory store'a merge et (idempotent: ayni id
    /// icin mevcut entry oncelikli — server snapshot'i sadece yoksa ekler).
    ///
    /// Implementasyon defensively coded: backend henuz endpoint'i serve
    /// etmiyor olabilir. Hata firlatabilir; cagiran tarafin try? veya catch
    /// ile silently degerlendirmesi beklenir.
    func hydrate(sessionId: String) async throws
}

/// Bridge -> Domain seviyesindeki subagent guncelleme tipi.
/// Data katmanindaki mapper bu tipi olusturur, Domain repository'si tuketir.
enum SubagentUpdate: Sendable, Equatable {
    /// Yeni bir subagent olustu.
    case spawn(Subagent)

    /// Calisan bir subagent'a aktivite/status guncellemesi geldi.
    case progress(taskId: String, sessionId: String, status: SubagentStatus, activity: String, updatedAt: Date)

    /// Subagent bitti (success/fail).
    case completed(
        taskId: String,
        sessionId: String,
        status: SubagentStatus,
        summary: String?,
        totalTokens: Int,
        toolUses: Int,
        durationMs: Int,
        completedAt: Date
    )
}
