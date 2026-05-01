import Foundation

/// Uygulama gorunum modu.
enum AppAppearance: String, Sendable, CaseIterable, Equatable {
    case system
    case light
    case dark

    /// Kullaniciya gosterilecek lokalize baslik.
    var localizedTitle: String {
        switch self {
        case .system: return String(localized: "settings.appearance.system")
        case .light: return String(localized: "settings.appearance.light")
        case .dark: return String(localized: "settings.appearance.dark")
        }
    }
}

/// Font boyutu secenegi.
enum AppFontSize: String, Sendable, CaseIterable, Equatable {
    case small
    case medium
    case large

    /// Kullaniciya gosterilecek lokalize baslik.
    var localizedTitle: String {
        switch self {
        case .small: return String(localized: "settings.fontSize.small")
        case .medium: return String(localized: "settings.fontSize.medium")
        case .large: return String(localized: "settings.fontSize.large")
        }
    }

    /// Dynamic type kategori eslestirmesi.
    var dynamicTypeSize: Double {
        switch self {
        case .small: return 0.85
        case .medium: return 1.0
        case .large: return 1.15
        }
    }
}

/// Bildirim tipi.
enum NotificationType: String, Sendable, CaseIterable, Equatable {
    case taskUpdates
    case approvalRequests
    case systemAlerts

    /// Kullaniciya gosterilecek lokalize baslik.
    var localizedTitle: String {
        switch self {
        case .taskUpdates: return String(localized: "settings.notification.taskUpdates")
        case .approvalRequests: return String(localized: "settings.notification.approvalRequests")
        case .systemAlerts: return String(localized: "settings.notification.systemAlerts")
        }
    }
}

/// Uygulama ayarlari domain modeli.
/// UserDefaults ile persist edilen tum ayarlar burada tanimlanir.
struct AppSettings: Sendable, Equatable {
    // MARK: - Bildirim Ayarlari

    /// Push bildirimleri aktif mi.
    var pushNotificationsEnabled: Bool

    /// Aktif bildirim tipleri.
    var enabledNotificationTypes: Set<NotificationType>

    // MARK: - Gorunum Ayarlari

    /// Uygulama gorunum modu.
    var appearance: AppAppearance

    /// Font boyutu secimi.
    var fontSize: AppFontSize

    // MARK: - Defaults

    /// Varsayilan ayarlar.
    static let defaults = AppSettings(
        pushNotificationsEnabled: true,
        enabledNotificationTypes: Set(NotificationType.allCases),
        appearance: .system,
        fontSize: .medium
    )
}
