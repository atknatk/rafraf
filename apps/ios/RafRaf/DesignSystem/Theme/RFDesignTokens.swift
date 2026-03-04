import SwiftUI

/// Kose yaricap tokenlari.
enum RFCornerRadius: Sendable {
    /// 8pt - kucuk bilesenler.
    static let small: CGFloat = 8
    /// 12pt - butonlar, text field.
    static let medium: CGFloat = 12
    /// 16pt - kartlar.
    static let large: CGFloat = 16
    /// 20pt - buyuk kartlar, hero alanlari.
    static let extraLarge: CGFloat = 20
    /// 100pt - capsule/pill sekli.
    static let pill: CGFloat = 100
}

/// Golge tanimlari.
enum RFShadow {
    struct ShadowSpec: Sendable {
        let color: Color
        let radius: CGFloat
        let x: CGFloat
        let y: CGFloat
    }

    static let subtle = ShadowSpec(
        color: .black.opacity(0.04), radius: 2, x: 0, y: 1
    )
    static let medium = ShadowSpec(
        color: .black.opacity(0.08), radius: 8, x: 0, y: 4
    )
    static let elevated = ShadowSpec(
        color: .black.opacity(0.12), radius: 16, x: 0, y: 8
    )
    static let prominent = ShadowSpec(
        color: .black.opacity(0.16), radius: 24, x: 0, y: 12
    )
}

/// Animasyon tokenlari.
enum RFAnimation {
    /// Duyarli spring - genel kullanim.
    static let springResponsive = Animation.spring(response: 0.35, dampingFraction: 0.7)
    /// Hizli spring - buton press, kucuk etkilesimler.
    static let springSnappy = Animation.spring(response: 0.25, dampingFraction: 0.8)
    /// Yavas spring - buyuk gecisler.
    static let springGentle = Animation.spring(response: 0.5, dampingFraction: 0.85)
    /// Standart ease - basit gecisler.
    static let easeDefault = Animation.easeInOut(duration: 0.2)
    /// Yavas reveal - icerik gorunumleri.
    static let easeSlowReveal = Animation.easeOut(duration: 0.4)
}

/// Yukseklik seviyesi - katmanli golge icin.
enum RFElevationLevel: Sendable {
    case low
    case medium
    case high
}
