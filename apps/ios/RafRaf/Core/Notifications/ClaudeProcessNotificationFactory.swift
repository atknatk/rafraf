import Foundation
@preconcurrency import UserNotifications

/// V1.x SLIM (Item 11) — Claude subprocess supervisor lokal bildirim turleri.
///
/// Spec: `shared/feature-specs/V1x-claude-supervisor.md` §10 (rollout — local
/// notifications only V1.x; APNS escalation V2). Backend de paralel olarak
/// `ProactiveNotification` persist eder; bu factory in-process anlik OS
/// banner'i icindir.
public enum ClaudeProcessNotificationKind: Sendable, Hashable {
    case stalled
    case crashed
    case rateLimited

    /// Localizable.xcstrings key'leri — bridge "stalled / crashed /
    /// rate_limited" stringini hard-coded English uretiyor; kullanici
    /// gorduklerini iOS lokalizasyonu uzerinden okur.
    var titleKey: String {
        switch self {
        case .stalled: return "claude.process.notif.stalled.title"
        case .crashed: return "claude.process.notif.crashed.title"
        case .rateLimited: return "claude.process.notif.rateLimited.title"
        }
    }

    var bodyKey: String {
        switch self {
        case .stalled: return "claude.process.notif.stalled.body"
        case .crashed: return "claude.process.notif.crashed.body"
        case .rateLimited: return "claude.process.notif.rateLimited.body"
        }
    }
}

/// Test edilebilirlik icin protokol; UNUserNotificationCenter mock yolu acik.
public protocol ClaudeProcessNotificationFactoryProtocol: Sendable {
    func fire(
        sessionId: String,
        kind: ClaudeProcessNotificationKind,
        detail: String?
    ) async
}

/// Notification center add(_:) icin minimal protokol — testte mock edilir.
public protocol UNNotificationCenterScheduling: Sendable {
    func add(_ request: UNNotificationRequest) async throws
}

extension UNUserNotificationCenter: @unchecked Sendable, UNNotificationCenterScheduling {}

/// Lokal UserNotification factory.
///
/// De-dupe: identifier `"claude.process.<kind>.<sessionId>"` — OS ayni id'ye
/// gelen yeni request'i mevcut bildirimi update ederek coalesce eder.
/// Boylece tekrarlayan stale event'lar tek banner gosterir (spec §10 risk #2).
public final class ClaudeProcessNotificationFactory: ClaudeProcessNotificationFactoryProtocol {
    private let center: UNNotificationCenterScheduling
    private let logger = AppLogger.logger(for: "ClaudeProcessNotif")

    public init(center: UNNotificationCenterScheduling = UNUserNotificationCenter.current()) {
        self.center = center
    }

    public func fire(
        sessionId: String,
        kind: ClaudeProcessNotificationKind,
        detail: String?
    ) async {
        let content = UNMutableNotificationContent()
        content.title = String(localized: String.LocalizationValue(kind.titleKey))
        let bodyTemplate = String(localized: String.LocalizationValue(kind.bodyKey))
        content.body = format(template: bodyTemplate, sessionId: sessionId, detail: detail)
        content.sound = .default
        content.userInfo = [
            "sessionId": sessionId,
            "kind": String(describing: kind)
        ]
        // OS coalesce — ayni session+kind bir kez goruntulenir.
        let identifier = "claude.process.\(String(describing: kind)).\(sessionId)"
        let request = UNNotificationRequest(
            identifier: identifier,
            content: content,
            trigger: nil // immediate
        )
        do {
            try await center.add(request)
            logger.info("notif scheduled - \(identifier, privacy: .public)")
        } catch {
            logger.error("notif add failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// `%@` placeholder'larini doldurur — fazlalari korunur (Localizable
    /// templates yalnizca varolanlari kullanir).
    private func format(template: String, sessionId: String, detail: String?) -> String {
        var output = template
        if output.contains("%session%") {
            output = output.replacingOccurrences(of: "%session%", with: sessionPrefix(sessionId))
        }
        if output.contains("%detail%") {
            let safeDetail = (detail ?? "").prefix(120)
            output = output.replacingOccurrences(of: "%detail%", with: String(safeDetail))
        }
        return output
    }

    private func sessionPrefix(_ sessionId: String) -> String {
        String(sessionId.prefix(8))
    }
}
