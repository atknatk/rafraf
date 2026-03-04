import SwiftUI

/// RafRaf tipografi sistemi.
/// Tum font tanimlari buradan yapilir.
enum RFTypography {
    /// Display - auth ekranlari, hero alanlari icin.
    static let display: Font = .system(size: 34, weight: .bold, design: .rounded)

    /// Buyuk baslik - ekran basliklari icin.
    static let largeTitle: Font = .largeTitle.weight(.bold)

    /// Baslik - section basliklari icin.
    static let title: Font = .title2.weight(.bold)

    /// Alt baslik.
    static let subtitle: Font = .title3.weight(.semibold)

    /// Headline - kart basliklari icin.
    static let headline: Font = .headline.weight(.semibold)

    /// Govde metni.
    static let body: Font = .body

    /// Buyuk govde - onemli metin icin.
    static let bodyLarge: Font = .callout

    /// Govde metni - kalin.
    static let bodyBold: Font = .body.weight(.semibold)

    /// Kucuk metin.
    static let caption: Font = .caption

    /// Kucuk metin - kalin.
    static let captionBold: Font = .caption.weight(.semibold)

    /// Overline - section etiketleri, metadata.
    static let overline: Font = .caption2.weight(.bold)

    /// Buton metni.
    static let button: Font = .body.weight(.semibold)

    /// Tab bar metni.
    static let tabBar: Font = .caption2

    /// Kod metni - monospaced.
    static let code: Font = .system(.body, design: .monospaced)
}
