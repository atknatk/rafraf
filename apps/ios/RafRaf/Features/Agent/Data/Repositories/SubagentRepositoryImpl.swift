import Foundation
import os

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
