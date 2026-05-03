import Foundation

// V1.x SLIM — Bridge → backend → iOS Claude subprocess supervisor wire DTOs.
//
// Spec: `shared/feature-specs/V1x-claude-supervisor.md` §4 (wire shapes).
//
// > KESIN KURAL: tum CodingKeys explicit snake_case raw value'larla yazilir.
// > `convertFromSnakeCase` strategy YASAK (lesson: V1.x ack envelope wire-shape
// > bug; ApprovalQuestionDTO disiplini). Boylece WebSocketMessageRouter'in
// > `useDefaultKeys` decoder'i ile sema ↔ DTO binding tek dogru kontrat
// > kaynagidir.

/// Spec §4.1 — `event.claude.process.spawned`.
struct ClaudeProcessSpawnedDTO: Codable, Sendable, Equatable {
    let sessionId: String
    let pid: Int
    let startedAt: Date
    let model: String
    /// Argv (prompt haric — PII guard, spec §4.1).
    let args: [String]?
    let permissionMode: String?
    let projectDir: String?

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case pid
        case startedAt = "started_at"
        case model
        case args
        case permissionMode = "permission_mode"
        case projectDir = "project_dir"
    }
}

/// Spec §4.2 — `event.claude.process.healthcheck`.
/// status ∈ {starting, running, idle, stale, rate_limited, completed}.
struct ClaudeProcessHealthcheckDTO: Codable, Sendable, Equatable {
    let sessionId: String
    let pid: Int
    let status: String
    let lastStdoutAgeMs: Int?
    let currentTokens: Int?
    let memoryRssKb: Int?
    let cpuPercent1s: Double?
    let observedAt: Date
    /// Bridge rate_limit cache TTL (ileride doldurulabilir; SLIM: optional).
    let rateLimitResetsAt: Date?

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case pid
        case status
        case lastStdoutAgeMs = "last_stdout_age_ms"
        case currentTokens = "current_tokens"
        case memoryRssKb = "memory_rss_kb"
        case cpuPercent1s = "cpu_percent_1s"
        case observedAt = "observed_at"
        case rateLimitResetsAt = "rate_limit_resets_at"
    }
}

/// Spec §4.3 — `event.claude.process.stalled`.
struct ClaudeProcessStalledDTO: Codable, Sendable, Equatable {
    let sessionId: String
    let pid: Int
    let lastActivityAt: Date
    let staleForMs: Int
    let stderrTail: String
    let stderrTailTruncated: Bool
    let selfHealPending: Bool

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case pid
        case lastActivityAt = "last_activity_at"
        case staleForMs = "stale_for_ms"
        case stderrTail = "stderr_tail"
        case stderrTailTruncated = "stderr_tail_truncated"
        case selfHealPending = "self_heal_pending"
    }
}

/// Spec §4.4 — `event.claude.process.crashed`.
struct ClaudeProcessCrashedDTO: Codable, Sendable, Equatable {
    let sessionId: String
    let pid: Int
    let exitCode: Int
    /// "SIGKILL" / "" / nil — bos string clean-but-nonzero exit.
    let signal: String?
    let stderrTail: String?
    let durationMs: Int
    let crashedAt: Date

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case pid
        case exitCode = "exit_code"
        case signal
        case stderrTail = "stderr_tail"
        case durationMs = "duration_ms"
        case crashedAt = "crashed_at"
    }
}

/// Spec §4.5 — `event.claude.process.recovered`.
struct ClaudeProcessRecoveredDTO: Codable, Sendable, Equatable {
    let oldSessionId: String
    let newSessionId: String
    let recoveryReason: String
    let recoveredAt: Date

    enum CodingKeys: String, CodingKey {
        case oldSessionId = "old_session_id"
        case newSessionId = "new_session_id"
        case recoveryReason = "recovery_reason"
        case recoveredAt = "recovered_at"
    }
}

/// Spec §4.6 — `event.claude.process.diagnosed`.
struct ClaudeProcessDiagnosedDTO: Codable, Sendable, Equatable {
    let sessionId: String
    /// Bridge tarafinda hard-coded English (Q7 karari) — iOS displays as-is.
    let diagnosisText: String
    /// "retry" | "wait" | "manual" — spec §4.6.
    let recommendedAction: String
    let diagnosticTokensUsed: Int?
    let diagnosticDurationMs: Int?
    let diagnosedAt: Date

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case diagnosisText = "diagnosis_text"
        case recommendedAction = "recommended_action"
        case diagnosticTokensUsed = "diagnostic_tokens_used"
        case diagnosticDurationMs = "diagnostic_duration_ms"
        case diagnosedAt = "diagnosed_at"
    }
}

/// Spec §4.7 — `command.claude.process.retry` (iOS → bridge).
/// Outbound; iOS encode tarafinda explicit CodingKeys ile snake_case yazilir.
struct ClaudeProcessRetryRequestDTO: Codable, Sendable, Equatable {
    let sessionId: String
    let userId: String?

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case userId = "user_id"
    }
}
