import Foundation
import Observation
import os

/// V1.5 backend-originated approval question presenter.
///
/// Process-wide singleton (DI uzerinden injekte edilir) — `WebSocketMessageRouter`'in
/// `question` envelope handler'i `enqueue(question:)` cagirir; root view
/// `.sheet(item: $coordinator.activeRequest)` ile RFApprovalSheet sunar; sheet
/// karar callback'i `handleDecision(_:)` ile coordinator'a doner.
///
/// Concurrent questions for one user — design v1-permission-blockers §4.2 —
/// parallel subagents bir kullaniciya ayni anda birden fazla onay sorabilir.
/// SwiftUI `.sheet(item:)` tek instance'tir; coordinator queue tutar ve
/// karar verildikce sonrakine gecer (modal stacking yok).
///
/// Allow-once vs Allow-session (V1 yorumu):
/// `RFApprovalSheet` 3 secenek emit eder (.allowOnce / .allowSession / .deny).
/// Wire kontrati sadece `approved`/`rejected` bilir (T3.1 ApprovalDecision).
/// V1 icin allow* her ikisi -> `.approved`; session-allow note `"allow_session"`
/// olarak iletilir, backend bu note'u Faz4'te tuketebilir.
@Observable
@MainActor
final class ApprovalCoordinator {
    /// Aktif olarak gosterilen sheet request'i (nil ise sheet kapali).
    /// Root view bu degeri `.sheet(item:)` binding'i olarak kullanir.
    var activeRequest: ApprovalSheetRequest?

    /// Bekleyen sheet request kuyrugu (head once gosterilir).
    /// Test gozlemi icin `private(set)`.
    private(set) var queue: [ApprovalSheetRequest] = []

    /// Domain ID -> orijinal soru. handleDecision sirasinda submitDecisionUseCase'a
    /// gonderilecek approvalId'yi yeniden uretmek icin saklanir.
    private(set) var pendingQuestionsById: [String: ApprovalQuestion] = [:]

    private let submitDecisionUseCase: SubmitApprovalDecisionUseCase
    private let logger = AppLogger.logger(for: "ApprovalCoordinator")

    init(submitDecisionUseCase: SubmitApprovalDecisionUseCase) {
        self.submitDecisionUseCase = submitDecisionUseCase
    }

    // MARK: - Inbound

    /// WebSocket router tarafindan, decoded `question` envelope geldiginde cagrilir.
    /// Soruyu kuyruga ekler ve gerekiyorsa sunmaya baslar.
    /// - Parameter question: Backend'den gelen onay sorusu (domain modeli)
    func enqueue(question: ApprovalQuestion) {
        let sheetRequest = ApprovalMapper.toSheetRequest(question: question)
        pendingQuestionsById[sheetRequest.id] = question
        queue.append(sheetRequest)
        logger.info("Approval kuyruga eklendi: \(sheetRequest.id) tool=\(sheetRequest.toolName)")
        presentNext()
    }

    /// Sheet'in karar callback'i tarafindan cagrilir (allow_once / allow_session / deny).
    /// Wire'a uygun ApprovalDecision uretir, use case ile gonderir, kuyrugu ilerletir.
    /// - Parameter choice: RFApprovalSheet'in emit ettigi kullanici secimi
    func handleDecision(_ choice: ApprovalUserChoice) async {
        guard let request = activeRequest else {
            logger.warning("handleDecision aktif request yokken cagrildi (no-op)")
            return
        }

        // Aktif request'i hemen temizle — UI bir sonraki sheet'e tutarli geciyor.
        activeRequest = nil
        let originalQuestion = pendingQuestionsById.removeValue(forKey: request.id)

        let approvalId = originalQuestion?.id ?? request.id
        let decision: ApprovalDecision
        let note: String?
        switch choice {
        case .allowOnce:
            decision = .approved
            note = nil
        case .allowSession:
            // V1: backend henuz "allow_session" notunu kullanmiyor; future Faz4 hook.
            decision = .approved
            note = ApprovalUserChoice.allowSession.rawValue
        case .deny:
            decision = .rejected
            note = nil
        }

        do {
            try await submitDecisionUseCase.execute(
                approvalId: approvalId,
                decision: decision,
                note: note
            )
            logger.info("Approval karari iletildi: \(approvalId) -> \(decision.rawValue)")
        } catch {
            // Submit basarisiz — V1.5 kapsami: kullaniciya retry UI vermiyor; backend
            // tarafi bridge timeout (V1.4) ile auto-deny duser. Hata structured log'a
            // dusurulur, sonraki sheet sunulmaya devam edilir.
            logger.error("Approval karari iletilemedi: \(approvalId) — \(error.localizedDescription)")
        }

        presentNext()
    }

    // MARK: - Test Hooks

    /// Test/cleanup amacli — coordinator'i bos duruma resetle.
    func reset() {
        activeRequest = nil
        queue.removeAll()
        pendingQuestionsById.removeAll()
    }

    // MARK: - Private

    /// Bir sonraki bekleyen request'i activeRequest yapar (sunma).
    /// Kural: `activeRequest` zaten doluysa hicbir sey yapma — sheet karar
    /// vermeden ikinci sheet acilmasin (modal stacking yok).
    private func presentNext() {
        guard activeRequest == nil else { return }
        guard !queue.isEmpty else { return }
        let next = queue.removeFirst()
        activeRequest = next
        logger.info("Approval sheet sunuldu: \(next.id)")
    }
}
