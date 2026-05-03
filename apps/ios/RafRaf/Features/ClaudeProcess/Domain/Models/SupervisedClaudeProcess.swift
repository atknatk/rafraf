import Foundation

/// V1.x SLIM — Bridge supervisor tarafindan izlenen tek bir claude subprocess.
///
/// Spec: `shared/feature-specs/V1x-claude-supervisor.md` §4 (wire shapes).
///
/// > NAMING GUARD: Mevcut `Features/Agent/Domain/Models/ClaudeProcess.swift`
/// > legacy psutil-driven heartbeat verisini temsil eder (apps/_archive Python
/// > v0.1 yolundan kalan kontrat). Bu yeni tip ona dokunulmaz; ad
/// > `SupervisedClaudeProcess` olarak farklilastirildi (spec Q2 kararina gore).
///
/// Bridge `event.claude.process.spawned` envelope'undan ilk olusturulur,
/// sonraki healthcheck/stalled/diagnosed/crashed/recovered envelope'lari
/// alanlari yerinde gunceller (immutable degil — repository state diff yapar).
public struct SupervisedClaudeProcess: Identifiable, Sendable, Hashable {
    /// Bridge `session_id` — supervisor instance'inin benzersiz kimligi.
    /// `Identifiable` icin id olarak kullanilir.
    public let id: String
    /// Iki adli alanlar: `id == sessionId` — kullanici kodunda her ikisi de
    /// okunabilir olsun diye explicit tutuldu.
    public var sessionId: String { id }

    /// OS process ID. Supervisor `Register` cagrisindaki ilk PID; restart
    /// olursa repository yeni bir kayit olusturur (PID degisirse bir oncekini
    /// `crashed` veya `completed` saymak supervisor'in sorumlulugundadir).
    public let pid: Int

    /// Aktif yasam dongusu durumu — spec §3.
    public var state: ClaudeProcessState

    /// Spawn timestamp (bridge `started_at`).
    public let startedAt: Date

    /// Son healthcheck tarafindan rapor edilen timestamp (probe loop). Banner
    /// "X saniye once" ozelligi icin kullanilir.
    public var lastObservedAt: Date

    /// Claude model adi (`claude-sonnet-4-7`). Spec §4.1 — "unknown" defaultu
    /// `OnInit.SetModel` race'inden korur.
    public let model: String

    /// Calistigi proje dizini (bridge `project_dir`). UI'da banner detaylari
    /// icin ileride kullanilabilir; SLIM scope'da log/debug.
    public let projectDir: String?

    /// `event.claude.process.stalled` payload'undan gelen son stderr kuyrugu
    /// (8 KiB cap). Banner ileride detail sheet'te gosterecek (V1.(x+1)).
    public var lastStderrTail: String?

    /// `event.claude.process.diagnosed` payload'undan gelen ana metin (4 KiB).
    /// Banner mavi durumda asina dusurulur.
    public var diagnosisText: String?

    /// Diagnostic'in onerdigi action — "retry" / "wait" / "manual".
    public var recommendedAction: String?

    /// `event.claude.process.crashed` payload'undan exit code.
    public var exitCode: Int?

    /// Crash sirasindaki sinyal ("SIGKILL" vb.). Clean-but-nonzero exit'te ""
    /// ya da nil olur.
    public var signal: String?

    /// Rate-limit window expiry — `event.claude.process.healthcheck`
    /// payload'unda bridge tarafindan iletilir (rate_limit cache sonu).
    /// SLIM: bridge bu alani henuz dolduruyor olmayabilir; nil ise banner
    /// generic "Rate limited" gosterir.
    public var rateLimitResetsAt: Date?

    public init(
        id: String,
        pid: Int,
        state: ClaudeProcessState,
        startedAt: Date,
        lastObservedAt: Date,
        model: String,
        projectDir: String? = nil,
        lastStderrTail: String? = nil,
        diagnosisText: String? = nil,
        recommendedAction: String? = nil,
        exitCode: Int? = nil,
        signal: String? = nil,
        rateLimitResetsAt: Date? = nil
    ) {
        self.id = id
        self.pid = pid
        self.state = state
        self.startedAt = startedAt
        self.lastObservedAt = lastObservedAt
        self.model = model
        self.projectDir = projectDir
        self.lastStderrTail = lastStderrTail
        self.diagnosisText = diagnosisText
        self.recommendedAction = recommendedAction
        self.exitCode = exitCode
        self.signal = signal
        self.rateLimitResetsAt = rateLimitResetsAt
    }
}

/// Banner'in goruntuleyecegi anlik durum — repository tarafindan
/// `SupervisedClaudeProcess`'ten projekte edilir.
///
/// Spec banner state machine (kullanici brifi):
///   running/idle/completed → banner GIZLI (state nil)
///   stale/diagnosing/rate_limited/crashed/recovered → banner GORUNUR
public struct ClaudeProcessBannerState: Sendable, Hashable {
    public let sessionId: String
    public let state: ClaudeProcessState
    /// Spec §3 stalled.stderr_tail / diagnosed.diagnosis_text gibi serbest metin.
    public let detail: String?
    /// Crash exit code (banner subtitle'da gosterilir).
    public let exitCode: Int?
    /// Rate-limit window expiry (banner "until {time}" iletisi).
    public let rateLimitResetsAt: Date?

    public init(
        sessionId: String,
        state: ClaudeProcessState,
        detail: String? = nil,
        exitCode: Int? = nil,
        rateLimitResetsAt: Date? = nil
    ) {
        self.sessionId = sessionId
        self.state = state
        self.detail = detail
        self.exitCode = exitCode
        self.rateLimitResetsAt = rateLimitResetsAt
    }

    /// Banner'in goruntulenip goruntulenmeyecegi.
    public var isVisible: Bool {
        switch state {
        case .running, .idle, .completed, .starting:
            return false
        case .stale, .diagnosing, .rateLimited, .crashed, .recovered:
            return true
        }
    }
}
