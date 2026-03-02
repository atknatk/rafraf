import SwiftUI

/// RafRaf tipografi sistemi.
/// Tum font tanimlari buradan yapilir.
enum RFTypography {
    /// Buyuk baslik - ekran basliklari icin.
    static let largeTitle: Font = .largeTitle.weight(.bold)

    /// Baslik - section basliklari icin.
    static let title: Font = .title2.weight(.semibold)

    /// Alt baslik.
    static let subtitle: Font = .title3.weight(.medium)

    /// Govde metni.
    static let body: Font = .body

    /// Govde metni - kalin.
    static let bodyBold: Font = .body.weight(.semibold)

    /// Kucuk metin.
    static let caption: Font = .caption

    /// Kucuk metin - kalin.
    static let captionBold: Font = .caption.weight(.semibold)

    /// Buton metni.
    static let button: Font = .body.weight(.semibold)

    /// Tab bar metni.
    static let tabBar: Font = .caption2
}
