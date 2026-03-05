import UIKit

/// Haptic geri bildirim yoneticisi.
/// AI olaylarina gore dogru haptic tipini tetikler.
@MainActor
enum HapticManager {

    /// Mesaj gonderildi.
    static func messageSent() {
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
    }

    /// AI cevabi tamamlandi.
    static func responseReceived() {
        UIImpactFeedbackGenerator(style: .soft).impactOccurred()
    }

    /// Hata olustu.
    static func error() {
        UINotificationFeedbackGenerator().notificationOccurred(.error)
    }

    /// Basari bildirimi.
    static func success() {
        UINotificationFeedbackGenerator().notificationOccurred(.success)
    }

    /// Uyari bildirimi.
    static func warning() {
        UINotificationFeedbackGenerator().notificationOccurred(.warning)
    }

    /// Secim degistirme (tab switch, picker).
    static func selection() {
        UISelectionFeedbackGenerator().selectionChanged()
    }

    /// Yer imi eklendi.
    static func bookmarked() {
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
    }

    /// Komut paleti acildi.
    static func commandPaletteOpened() {
        UIImpactFeedbackGenerator(style: .rigid).impactOccurred()
    }
}
