import SwiftUI

/// RafRaf renk paleti.
/// Tum renkler buradan tanimlanir, feature ekranlarinda dogrudan Color literal YASAK.
/// Dark mode destegi: Sistem temasina gore otomatik renk gecisi saglanir.
enum RFColors {
    // MARK: - Primary

    static let primary = Color("Primary", bundle: .main)
    static let primaryLight = Color("PrimaryLight", bundle: .main)
    static let primaryDark = Color("PrimaryDark", bundle: .main)

    // MARK: - Secondary

    static let secondary = Color("Secondary", bundle: .main)

    // MARK: - Background

    static let background = Color("Background", bundle: .main)
    static let surfacePrimary = Color("SurfacePrimary", bundle: .main)
    static let surfaceSecondary = Color("SurfaceSecondary", bundle: .main)

    // MARK: - Text

    static let textPrimary = Color("TextPrimary", bundle: .main)
    static let textSecondary = Color("TextSecondary", bundle: .main)
    static let textTertiary = Color("TextTertiary", bundle: .main)

    // MARK: - Semantic (Dark mode uyumlu)

    static let success = Color.green
    static let warning = Color.orange
    static let error = Color.red
    static let info = Color.blue

    // MARK: - Fallbacks (Asset catalog olmadan kullanilabilir, dark mode uyumlu)

    /// Primary renk - dark mode'da acik mavi, light mode'da koyu mavi.
    static let fallbackPrimary = Color(
        light: Color(red: 0.106, green: 0.165, blue: 0.290),
        dark: Color(red: 0.357, green: 0.608, blue: 0.835)
    )

    /// Arkaplan rengi - sistem arkaplanini kullanir (dark mode uyumlu).
    static let fallbackBackground = Color(.systemBackground)

    /// Yuzey rengi - ikincil arkaplan (dark mode uyumlu).
    static let fallbackSurface = Color(.secondarySystemBackground)

    /// Birincil metin rengi (dark mode uyumlu).
    static let fallbackTextPrimary = Color(.label)

    /// Ikincil metin rengi (dark mode uyumlu).
    static let fallbackTextSecondary = Color(.secondaryLabel)

    /// Ucuncul metin rengi (dark mode uyumlu).
    static let fallbackTextTertiary = Color(.tertiaryLabel)

    // MARK: - Chat Bubble (Dark mode uyumlu)

    /// AI mesaj baloncugu arka plan rengi.
    static let aiBubble = Color(
        light: Color(red: 0.910, green: 0.941, blue: 0.996),
        dark: Color(red: 0.118, green: 0.227, blue: 0.373)
    )

    /// Kullanici mesaj baloncugu arka plan rengi.
    static let userBubble = Color(
        light: Color(red: 0.106, green: 0.165, blue: 0.290),
        dark: Color(red: 0.357, green: 0.608, blue: 0.835)
    )

    // MARK: - Divider

    /// Ayirici cizgi rengi (dark mode uyumlu).
    static let divider = Color(.separator)
}

// MARK: - Color Extension for Dark Mode

extension Color {
    /// Light ve dark mode icin farkli renkler tanimlar.
    init(light: Color, dark: Color) {
        self.init(uiColor: UIColor { traitCollection in
            switch traitCollection.userInterfaceStyle {
            case .dark:
                return UIColor(dark)
            default:
                return UIColor(light)
            }
        })
    }
}
