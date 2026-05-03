import Foundation

/// V1.x SLIM — Claude subprocess supervisor repository protokolu.
///
/// Spec: `shared/feature-specs/V1x-claude-supervisor.md` §7
/// (iOS file ownership, banner + retry slim scope).
///
/// Domain Data/Network tiplerine bagli kalmaz — `SupervisedClaudeProcess`,
/// `ClaudeProcessBannerState` salt domain tipleridir.
public protocol ClaudeProcessRepository: Sendable {
    /// Belirli bir session icin supervize edilen process'i stream eder.
    /// Process kaydi yoksa `nil` yayinlar; spawn ile birlikte canli model
    /// yayinlanir; her wire envelope (healthcheck/stalled/...) mutate eder.
    func observeProcesses(sessionId: String) async -> AsyncStream<SupervisedClaudeProcess?>

    /// Banner state'i icin yardimci stream — yine `nil` gizli, dolu gorunur.
    /// `RFClaudeProcessBanner` bunu dogrudan tuketir.
    func observeBanner(sessionId: String) async -> AsyncStream<ClaudeProcessBannerState?>

    /// Mevcut anlik snapshot (test / UI baslangic icin).
    func currentProcess(sessionId: String) async -> SupervisedClaudeProcess?

    /// Kullanici "Retry" butonuna bastiginda cagirilir.
    /// Spec §4.7 — `command.claude.process.retry` envelope'ini WebSocket
    /// uzerinden bridge'e yollar.
    func requestRetry(sessionId: String) async throws

    /// Banner'i kapatir (kullanici X butonuna bastiginda).
    /// State kayidini silmez — sadece bannerStream'e nil yayinlar.
    func dismissBanner(sessionId: String) async

    // MARK: - Internal write API (bridge envelope handler'lari icin)

    /// Wire envelope'tan gelen process state degisikligini uygular.
    /// Bridge envelope'lari direkt repository'ye yazar (mapper rolu burada
    /// minimal); spec §4 wire shape'leri korunur.
    func applySpawned(
        sessionId: String,
        pid: Int,
        startedAt: Date,
        model: String,
        projectDir: String?
    ) async

    /// Healthcheck — state guncellemesi + observed timestamp.
    func applyHealthcheck(
        sessionId: String,
        state: ClaudeProcessState,
        observedAt: Date,
        rateLimitResetsAt: Date?
    ) async

    /// Stale — banner sariya doner, stderr_tail saklanir.
    func applyStalled(
        sessionId: String,
        stderrTail: String,
        observedAt: Date
    ) async

    /// Diagnosed — banner mavi: diagnosis_text + recommended_action.
    func applyDiagnosed(
        sessionId: String,
        diagnosisText: String,
        recommendedAction: String,
        observedAt: Date
    ) async

    /// Crashed — terminal red banner, retry button.
    func applyCrashed(
        sessionId: String,
        exitCode: Int,
        signal: String?,
        stderrTail: String?,
        observedAt: Date
    ) async

    /// Recovered — yesil flash, sonra 3s'de otomatik dismiss.
    func applyRecovered(
        sessionId: String,
        observedAt: Date
    ) async
}
