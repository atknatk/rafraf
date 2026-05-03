import Foundation

/// V1.x SLIM — Bridge tarafindan supervize edilen claude subprocess yasam dongusu.
///
/// Spec: `shared/feature-specs/V1x-claude-supervisor.md` §3 (state table).
/// Bridge state string'leri ile birebir eslesir; bilinmeyen / future bir
/// degeri en yakin bilinen duruma dusurur (forward-compat).
public enum ClaudeProcessState: String, Sendable, Hashable, CaseIterable {
    /// Process spawn edildi, henuz ilk stdout gelmedi.
    case starting
    /// Stdout akiyor, normal calisma.
    case running
    /// Stdout `idle_threshold` (default 30s) askiya alindi.
    case idle
    /// `stale_threshold` (default 90s) askiya alindi — diagnostic on the way.
    case stale
    /// Diagnostic claude calisiyor (banner: blue, "Diagnosing...").
    case diagnosing
    /// Rate-limit cache hit — kullanici belirli bir saate kadar beklemeli.
    case rateLimited = "rate_limited"
    /// Subprocess exit non-zero (terminal — Retry button gosterilir).
    case crashed
    /// Subprocess EventSessionResult ile temiz cikti.
    case completed
    /// Stale → running geri donusu (3s sonra otomatik dismiss).
    case recovered

    /// Bilinmeyen wire string'ini en yakin bilinen duruma dusurur.
    /// Bridge ileride yeni bir state eklerse UI bozulmaz.
    public static func from(rawString raw: String) -> ClaudeProcessState {
        if let exact = ClaudeProcessState(rawValue: raw) {
            return exact
        }
        return .running
    }
}
