import UIKit

/// RafRaf haptic geri bildirim yardimcisi.
/// Tum haptic cagrilari buradan yapilir, tutarlilik icin.
@MainActor
enum RFHaptics: Sendable {
    /// Darbe geri bildirimi - buton tiklamalari icin.
    static func impact(_ style: UIImpactFeedbackGenerator.FeedbackStyle = .light) {
        let generator = UIImpactFeedbackGenerator(style: style)
        generator.impactOccurred()
    }

    /// Bildirim geri bildirimi - basari, hata, uyari.
    static func notification(_ type: UINotificationFeedbackGenerator.FeedbackType) {
        let generator = UINotificationFeedbackGenerator()
        generator.notificationOccurred(type)
    }

    /// Secim geri bildirimi - tab, filtre, picker degisimleri.
    static func selection() {
        let generator = UISelectionFeedbackGenerator()
        generator.selectionChanged()
    }
}
