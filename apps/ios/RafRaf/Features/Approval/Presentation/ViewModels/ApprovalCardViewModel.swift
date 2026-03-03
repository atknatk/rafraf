import Foundation
import os

/// Onay karti ViewModel.
/// Countdown timer, karar gonderme ve animasyon durumunu yonetir.
@Observable
@MainActor
final class ApprovalCardViewModel {
    // MARK: - State

    /// Aktif onay sorusu.
    var question: ApprovalQuestion?
    /// Kalan sure (saniye).
    var remainingSeconds: Int = 0
    /// Karar gonderiliyor mu.
    var isSubmitting: Bool = false
    /// Kart gorunur mu (animasyon icin).
    var isVisible: Bool = false
    /// Kullanici karari gonderildi mi.
    var isDecided: Bool = false
    /// Hata mesaji.
    var errorMessage: String?

    // MARK: - Private

    private let submitDecisionUseCase: SubmitApprovalDecisionUseCase
    /// nonisolated(unsafe) — deinit'te erisilebilmesi icin gerekli (Swift 6 concurrency).
    nonisolated(unsafe) private var timerTask: Task<Void, Never>?
    private let logger = AppLogger.logger(for: "ApprovalCard")

    // MARK: - Init

    init(submitDecisionUseCase: SubmitApprovalDecisionUseCase) {
        self.submitDecisionUseCase = submitDecisionUseCase
    }

    deinit {
        timerTask?.cancel()
    }

    // MARK: - Actions

    /// Yeni onay sorusunu gosterir ve countdown baslatir.
    /// - Parameter newQuestion: Backend'den gelen onay sorusu
    func showQuestion(_ newQuestion: ApprovalQuestion) {
        // Mevcut timer'i iptal et
        timerTask?.cancel()

        question = newQuestion
        remainingSeconds = newQuestion.timeoutSeconds
        isDecided = false
        isSubmitting = false
        errorMessage = nil
        isVisible = true

        logger.info("Approval sorusu gosteriliyor: \(newQuestion.id)")
        startCountdown()
    }

    /// Kullanici kararini gonderir.
    /// - Parameters:
    ///   - optionId: Secilen secenek ID'si
    ///   - decision: Onay karari (approved/rejected)
    func submitDecision(optionId: String, decision: ApprovalDecision) async {
        guard let currentQuestion = question, !isDecided else { return }

        isSubmitting = true
        errorMessage = nil

        do {
            try await submitDecisionUseCase.execute(
                approvalId: currentQuestion.id,
                decision: decision,
                note: nil
            )
            isDecided = true
            timerTask?.cancel()
            logger.info("Approval karari gonderildi: \(currentQuestion.id) -> \(decision.rawValue)")
        } catch {
            errorMessage = String(localized: "approval.error.submitFailed")
            logger.error("Approval karari gonderilemedi: \(error.localizedDescription)")
        }

        isSubmitting = false
    }

    /// Karti kapatir (karar sonrasi veya timeout sonrasi).
    func dismiss() {
        isVisible = false
        timerTask?.cancel()

        // Animasyon tamamlandiktan sonra state temizle
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(500))
            self.question = nil
            self.isDecided = false
            self.remainingSeconds = 0
        }
    }

    /// Kalan surenin yuzdesi (0.0 - 1.0).
    var progressFraction: Double {
        guard let currentQuestion = question, currentQuestion.timeoutSeconds > 0 else {
            return 0.0
        }
        return Double(remainingSeconds) / Double(currentQuestion.timeoutSeconds)
    }

    /// Kategori tehlikeli mi (kirmizi vurgu icin).
    var isDangerousCategory: Bool {
        guard let currentQuestion = question else { return false }
        return currentQuestion.category == .destructive || currentQuestion.category == .deploy
    }

    // MARK: - Private

    private func startCountdown() {
        timerTask = Task { @MainActor [weak self] in
            guard let self else { return }

            while self.remainingSeconds > 0 && !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard !Task.isCancelled else { return }
                self.remainingSeconds -= 1
            }

            guard !Task.isCancelled, !self.isDecided else { return }

            // Timeout: otomatik red gonder
            self.logger.info("Approval timeout: \(self.question?.id ?? "unknown")")
            await self.handleTimeout()
        }
    }

    private func handleTimeout() async {
        guard let currentQuestion = question, !isDecided else { return }

        isSubmitting = true
        do {
            try await submitDecisionUseCase.execute(
                approvalId: currentQuestion.id,
                decision: .rejected,
                note: "Timeout - otomatik red"
            )
            isDecided = true
            logger.info("Timeout karari gonderildi: \(currentQuestion.id) -> rejected")
        } catch {
            errorMessage = String(localized: "approval.error.timeoutFailed")
            logger.error("Timeout karari gonderilemedi: \(error.localizedDescription)")
        }
        isSubmitting = false
    }
}
