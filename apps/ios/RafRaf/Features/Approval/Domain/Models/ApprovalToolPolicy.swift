import Foundation

/// Spike #5 fallback agacindaki onay politikasi.
///
/// Tool isimlerine gore varsayilan davranis:
///   - read / grep / ls / glob / cat / pwd -> auto-allow (UI hic gosterilmez)
///   - write / edit / bash / multiedit / patch -> ASK (modal sheet)
///   - WebFetch / WebSearch -> ASK
///   - Bash + safe shell command (ls / pwd / cat / which / echo) ->
///     fast-path allow (docs/08 host agent shell whitelist'i ile uyumlu)
///   - Tanimsiz tool -> ASK (guvenlik default'u)
///
/// Coordinator/UI tarafi bu enum'a gore ya prompt'u gosterir ya da onay
/// kayitsiz gecirir. Pure logic — hicbir yan etkisi yok, test edilebilir.
enum ApprovalDecisionPolicy: Sendable, Equatable {
    /// Hicbir UI gosterme; otomatik olarak izin ver.
    case autoAllow
    /// Modal sheet ac, kullanici karar versin.
    case prompt(risk: ApprovalRiskLevel)
    /// 30s timeout sonrasi otomatik reddet (kullanici cevap vermezse).
    case autoDenyOnTimeout
}

/// UI tarafinda renk + ikon icin kullanilan risk siniflandirmasi.
enum ApprovalRiskLevel: String, Sendable, Equatable, CaseIterable {
    case low
    case medium
    case high
}

/// Tool ismi -> politika cozumleyici. Sadece pure functions.
enum ApprovalToolPolicy {

    /// Bash icin "guvenli" oldugu kabul edilen alt komutlar (docs/08 ile
    /// uyumlu). Bu listenin disinda kalan herhangi bir bash komutu prompt'a
    /// dusurulur.
    static let safeBashCommands: Set<String> = [
        "ls", "pwd", "cat", "which", "echo", "head", "tail", "wc", "date"
    ]

    /// Read-only / inspection tool'lari — auto-allow.
    static let readOnlyTools: Set<String> = [
        "read", "grep", "ls", "glob", "cat", "pwd", "find"
    ]

    /// Yuksek riskli (write/destructive) tool'lar.
    static let highRiskTools: Set<String> = [
        "write", "edit", "multiedit", "patch", "delete"
    ]

    /// Tek seferlik sorulmasi sart olan ag tool'lari.
    static let networkTools: Set<String> = [
        "WebFetch", "WebSearch"
    ]

    /// Verilen tool ismi + ilk command argumani icin bir politika dondurur.
    /// - Parameters:
    ///   - toolName: Bridge tarafindan gonderilen tool adi (case-insensitive
    ///     read-only kontrolunde, network tool'larinda case-sensitive). Sebebi:
    ///     Read/Edit Claude tool'lari camelCase iken `WebFetch` net olmak
    ///     zorunda.
    ///   - command: Bash tool'lari icin baslangic argumani (whitespace-trimmed).
    ///     Diger tool'larda `nil` verilir.
    /// - Returns: Politika kararini dondurur.
    static func decide(
        toolName: String,
        command: String? = nil
    ) -> ApprovalDecisionPolicy {
        let trimmed = toolName.trimmingCharacters(in: .whitespacesAndNewlines)
        let lowered = trimmed.lowercased()

        // 1. Read-only auto-allow
        if readOnlyTools.contains(lowered) {
            return .autoAllow
        }

        // 2. Network tool'lari her zaman prompt — risk medium.
        if networkTools.contains(trimmed) {
            return .prompt(risk: .medium)
        }

        // 3. Bash — komuta gore degerlendir.
        if lowered == "bash" {
            if let command = command,
               let firstToken = firstToken(of: command),
               safeBashCommands.contains(firstToken.lowercased()) {
                return .autoAllow
            }
            return .prompt(risk: .high)
        }

        // 4. Yuksek riskli tool'lar -> high prompt.
        if highRiskTools.contains(lowered) {
            return .prompt(risk: .high)
        }

        // 5. Default: prompt + medium risk.
        return .prompt(risk: .medium)
    }

    /// Bir komuttaki ilk token (boslugu bolen ilk parca).
    static func firstToken(of command: String) -> String? {
        let trimmed = command.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if let first = trimmed.split(separator: " ", maxSplits: 1).first {
            return String(first)
        }
        return trimmed
    }

    /// Kullanicinin "Allow always" karari icin oturum kapsamli bir scope
    /// anahtari uretir. Ayni tool + ayni komut tekrar geldiginde policy
    /// `autoAllow` doner. Coordinator bu anahtari ApprovalSession'a
    /// kaydedebilir.
    static func sessionAllowKey(toolName: String, command: String?) -> String {
        if let command, !command.isEmpty {
            return "\(toolName.lowercased())::\(command)"
        }
        return toolName.lowercased()
    }
}

/// Allow-once / Allow-always-for-session / Deny secimleri.
enum ApprovalUserChoice: String, Sendable, Equatable, CaseIterable {
    case allowOnce = "allow_once"
    case allowSession = "allow_session"
    case deny
}

/// Session boyunca kullanicinin "Allow always" dedigi tool+command
/// kombinasyonlarini takip eder. ApprovalCoordinator (ya da view) burayi
/// kullanir.
@MainActor
final class ApprovalSessionAllowList {
    private(set) var allowedKeys: Set<String> = []

    /// Kullanici Allow-always sectiginde anahtari ekler.
    func remember(key: String) {
        allowedKeys.insert(key)
    }

    /// Coordinator karar oncesinde bu helper'i kontrol eder.
    func contains(key: String) -> Bool {
        allowedKeys.contains(key)
    }

    /// Test/temizlik icin.
    func clear() {
        allowedKeys.removeAll()
    }

    /// Verilen tool + komut allow-list'te ise ApprovalDecisionPolicy.autoAllow
    /// donerek policy'yi by-pass eder.
    func policy(
        toolName: String,
        command: String?,
        defaultPolicy: ApprovalDecisionPolicy
    ) -> ApprovalDecisionPolicy {
        let key = ApprovalToolPolicy.sessionAllowKey(toolName: toolName, command: command)
        if contains(key: key) {
            return .autoAllow
        }
        return defaultPolicy
    }
}
