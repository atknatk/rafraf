import Foundation
import os

// MARK: - REST Hydration DTOs (Item 9)

/// Item 9 — `GET /api/v1/sessions/{session_id}/subagents` response satiri.
/// Backend dev paralel olarak endpoint'i ekliyor. Sema spec'te belirtildigi
/// gibi WS push DTO'lariyla ayni sekil; defensive: tum opsiyonel alanlar
/// nullable, decoder snake_case -> camelCase otomatik cevirir
/// (NetworkClient).
struct SubagentRestDTO: Decodable, Sendable {
    let id: String
    let parentId: String?
    let sessionId: String
    let status: String
    let name: String?
    let description: String?
    let promptPreview: String?
    let subagentType: String?
    let isolation: String?
    let summary: String?
    let totalTokens: Int?
    let toolUses: Int?
    let durationMs: Int?
    let activity: String?
    let startedAt: String?
    let completedAt: String?
    let updatedAt: String?
    let progressPercent: Double?
}

/// `SubagentRepository` implementasyonu.
///
/// In-memory actor cache uzerine kuruludur — bridge mesajlari `apply(update:)`
/// ile gelir, her degisiklikte aktif AsyncStream subscriber'lara guncel
/// liste yayilir.
///
/// Kalitisiz tasarim:
///   - `SubagentState` actor: tum mutasyon ve subscriber kaydi orada.
///   - `SubagentRepositoryImpl` thin wrapper: protocol uyumu icin.
///
/// Doc 10 §6.3.3.
final class SubagentRepositoryImpl: SubagentRepository, @unchecked Sendable {
    private let state = SubagentState()
    private let logger = AppLogger.logger(for: "SubagentRepository")
    /// Item 9 — REST hydration icin opsiyonel network istemcisi. nil verilirse
    /// `hydrate(sessionId:)` no-op (test / preview yolu).
    private let networkClient: NetworkClient?

    init(networkClient: NetworkClient? = nil) {
        self.networkClient = networkClient
    }

    func observeSubagents(sessionId: String) async -> AsyncStream<[Subagent]> {
        await state.subscribe(sessionId: sessionId)
    }

    func observeAllSubagents() async -> AsyncStream<[Subagent]> {
        await state.subscribeAll()
    }

    func currentSubagents(sessionId: String) async -> [Subagent] {
        await state.snapshot(sessionId: sessionId)
    }

    func currentAllSubagents() async -> [Subagent] {
        await state.snapshotAll()
    }

    func apply(update: SubagentUpdate) async {
        await state.apply(update)
        switch update {
        case .spawn(let sub):
            logger.info("subagent.spawned uygulandi - session: \(sub.sessionId), task: \(sub.id), name: \(sub.name)")
        case .progress(let taskId, let sessionId, let status, _, _):
            logger.debug("subagent.progress uygulandi - session: \(sessionId), task: \(taskId), status: \(status.rawValue)")
        case .completed(let taskId, let sessionId, let status, _, _, _, _, _):
            logger.info("subagent.completed uygulandi - session: \(sessionId), task: \(taskId), status: \(status.rawValue)")
        }
    }

    func clear(sessionId: String) async {
        await state.clear(sessionId: sessionId)
        logger.info("Subagent state temizlendi - session: \(sessionId)")
    }

    // MARK: - Item 9 — REST Hydration

    /// Backend snapshot'ini in-memory store'a merge eder. Idempotent:
    ///   - Mevcut id'li entry varsa korunur (in-memory state oncelikli, cunku
    ///     o WS push'tan yazildi — server snapshot eski olabilir).
    ///   - Mevcut entry yoksa REST satiri spawn olarak eklenir.
    func hydrate(sessionId: String) async throws {
        guard let networkClient else {
            logger.debug("hydrate: networkClient yok, no-op (test path)")
            return
        }

        let path = "/sessions/\(sessionId)/subagents"
        let dtos: [SubagentRestDTO] = try await networkClient.get(path: path)
        logger.info("hydrate: backend'den \(dtos.count) subagent geldi - session: \(sessionId)")

        for dto in dtos {
            // sessionId backend'den de gelir; defensive: parametreyi tercih et
            let canonicalSessionId = dto.sessionId.isEmpty ? sessionId : dto.sessionId
            let subagent = Self.subagent(from: dto, sessionId: canonicalSessionId)
            await state.mergeIfAbsent(subagent)
        }
    }

    // MARK: - DTO -> Domain mapping

    private static func subagent(from dto: SubagentRestDTO, sessionId: String) -> Subagent {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        // Fallback formatter — backend bazi alanlarda fractionalSeconds vermez.
        let fallbackFormatter = ISO8601DateFormatter()
        fallbackFormatter.formatOptions = [.withInternetDateTime]

        func parseDate(_ raw: String?) -> Date? {
            guard let raw, !raw.isEmpty else { return nil }
            return formatter.date(from: raw) ?? fallbackFormatter.date(from: raw)
        }

        let spawnedAt = parseDate(dto.startedAt) ?? Date()
        let updatedAt = parseDate(dto.updatedAt)
        let completedAt = parseDate(dto.completedAt)
        let status = SubagentStatus.from(rawString: dto.status)

        return Subagent(
            id: dto.id,
            sessionId: sessionId,
            parentTaskId: dto.parentId,
            name: dto.name ?? dto.subagentType ?? "subagent",
            description: dto.description,
            promptPreview: dto.promptPreview ?? "",
            subagentType: dto.subagentType,
            isolation: dto.isolation,
            status: status,
            summary: dto.summary,
            totalTokens: dto.totalTokens,
            toolUses: dto.toolUses,
            durationMs: dto.durationMs,
            activity: dto.activity,
            spawnedAt: spawnedAt,
            updatedAt: updatedAt,
            completedAt: completedAt
        )
    }
}

/// Thread-safe state actor.
///
/// `storage[sessionId]` -> sessionId altinda saklanan tum subagent kayitlari
/// (taskId -> Subagent). `continuations[sessionId]` -> aktif AsyncStream
/// continuation'lari (UUID -> Continuation). Yeni subscriber geldiginde anlik
/// snapshot yayilir; her mutasyondan sonra tum subscriber'lar guncel listeyi
/// alir.
private actor SubagentState {
    private var storage: [String: [String: Subagent]] = [:]
    private var continuations: [String: [UUID: AsyncStream<[Subagent]>.Continuation]] = [:]
    private var allContinuations: [UUID: AsyncStream<[Subagent]>.Continuation] = [:]

    func snapshot(sessionId: String) -> [Subagent] {
        sortedSubagents(in: sessionId)
    }

    func snapshotAll() -> [Subagent] {
        allSortedSubagents()
    }

    func subscribe(sessionId: String) -> AsyncStream<[Subagent]> {
        AsyncStream { continuation in
            let id = UUID()
            self.register(id: id, continuation: continuation, for: sessionId)
            // Initial snapshot
            continuation.yield(self.sortedSubagents(in: sessionId))
            continuation.onTermination = { @Sendable [weak self] _ in
                guard let self else { return }
                Task { await self.unregister(id: id, for: sessionId) }
            }
        }
    }

    func subscribeAll() -> AsyncStream<[Subagent]> {
        AsyncStream { continuation in
            let id = UUID()
            self.registerAll(id: id, continuation: continuation)
            continuation.yield(self.allSortedSubagents())
            continuation.onTermination = { @Sendable [weak self] _ in
                guard let self else { return }
                Task { await self.unregisterAll(id: id) }
            }
        }
    }

    func apply(_ update: SubagentUpdate) {
        switch update {
        case .spawn(let sub):
            var bucket = storage[sub.sessionId] ?? [:]
            // Spawn ayni id ile tekrar gelirse mevcudu koru, sadece yeni
            // metadata ile guncelle. Bu sayede UI'da zaten var olan progress
            // verisi kaybolmaz.
            if let existing = bucket[sub.id] {
                var merged = existing
                merged = Subagent(
                    id: sub.id,
                    sessionId: sub.sessionId,
                    parentTaskId: sub.parentTaskId ?? existing.parentTaskId,
                    name: sub.name,
                    description: sub.description ?? existing.description,
                    promptPreview: sub.promptPreview,
                    subagentType: sub.subagentType ?? existing.subagentType,
                    isolation: sub.isolation ?? existing.isolation,
                    status: existing.status, // mevcut yasam dongusu durumunu koru
                    summary: existing.summary,
                    totalTokens: existing.totalTokens,
                    toolUses: existing.toolUses,
                    durationMs: existing.durationMs,
                    activity: existing.activity,
                    spawnedAt: existing.spawnedAt, // ilk gorulen zaman korunur
                    updatedAt: existing.updatedAt,
                    completedAt: existing.completedAt
                )
                bucket[sub.id] = merged
            } else {
                bucket[sub.id] = sub
            }
            storage[sub.sessionId] = bucket
            yieldUpdate(for: sub.sessionId)

        case .progress(let taskId, let sessionId, let status, let activity, let updatedAt):
            guard var bucket = storage[sessionId], var existing = bucket[taskId] else {
                // Henuz spawn gormedik — progress'i sessizce yoksay.
                return
            }
            existing.status = status
            existing.activity = activity
            existing.updatedAt = updatedAt
            bucket[taskId] = existing
            storage[sessionId] = bucket
            yieldUpdate(for: sessionId)

        case .completed(let taskId, let sessionId, let status, let summary, let totalTokens, let toolUses, let durationMs, let completedAt):
            guard var bucket = storage[sessionId], var existing = bucket[taskId] else {
                return
            }
            existing.status = status
            existing.summary = summary
            existing.totalTokens = totalTokens
            existing.toolUses = toolUses
            existing.durationMs = durationMs
            existing.completedAt = completedAt
            existing.updatedAt = completedAt
            bucket[taskId] = existing
            storage[sessionId] = bucket
            yieldUpdate(for: sessionId)
        }
    }

    func clear(sessionId: String) {
        storage[sessionId] = nil
        yieldUpdate(for: sessionId)
    }

    /// Item 9 — REST hydration helper.
    /// In-memory entry varsa korur (cunku WS push daha taze), yoksa ekler.
    /// Idempotent: ayni id ikinci kez gelirse no-op.
    func mergeIfAbsent(_ subagent: Subagent) {
        var bucket = storage[subagent.sessionId] ?? [:]
        if bucket[subagent.id] == nil {
            bucket[subagent.id] = subagent
            storage[subagent.sessionId] = bucket
            yieldUpdate(for: subagent.sessionId)
        }
    }

    // MARK: - Private

    private func register(
        id: UUID,
        continuation: AsyncStream<[Subagent]>.Continuation,
        for sessionId: String
    ) {
        var bucket = continuations[sessionId] ?? [:]
        bucket[id] = continuation
        continuations[sessionId] = bucket
    }

    private func unregister(id: UUID, for sessionId: String) {
        guard var bucket = continuations[sessionId] else { return }
        bucket.removeValue(forKey: id)
        if bucket.isEmpty {
            continuations.removeValue(forKey: sessionId)
        } else {
            continuations[sessionId] = bucket
        }
    }

    private func registerAll(
        id: UUID,
        continuation: AsyncStream<[Subagent]>.Continuation
    ) {
        allContinuations[id] = continuation
    }

    private func unregisterAll(id: UUID) {
        allContinuations.removeValue(forKey: id)
    }

    private func yieldUpdate(for sessionId: String) {
        let snapshot = sortedSubagents(in: sessionId)
        if let bucket = continuations[sessionId] {
            for continuation in bucket.values {
                continuation.yield(snapshot)
            }
        }
        if !allContinuations.isEmpty {
            let allSnapshot = allSortedSubagents()
            for continuation in allContinuations.values {
                continuation.yield(allSnapshot)
            }
        }
    }

    private func sortedSubagents(in sessionId: String) -> [Subagent] {
        guard let bucket = storage[sessionId] else { return [] }
        return bucket.values.sorted { $0.spawnedAt < $1.spawnedAt }
    }

    private func allSortedSubagents() -> [Subagent] {
        storage.values
            .flatMap { $0.values }
            .sorted { $0.spawnedAt < $1.spawnedAt }
    }
}
