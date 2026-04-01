import SwiftUI

/// RafRaf renk paleti — Claude-inspired sicak tonlar.
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

    // MARK: - Semantic (Dark mode uyumlu, rafine tonlar)

    static let success = Color.rfAdaptive(
        light: Color(red: 0.20, green: 0.72, blue: 0.45),
        dark: Color(red: 0.30, green: 0.80, blue: 0.55)
    )
    static let warning = Color.rfAdaptive(
        light: Color(red: 0.90, green: 0.65, blue: 0.20),
        dark: Color(red: 0.95, green: 0.72, blue: 0.30)
    )
    static let error = Color.rfAdaptive(
        light: Color(red: 0.85, green: 0.28, blue: 0.28),
        dark: Color(red: 0.95, green: 0.40, blue: 0.40)
    )
    static let info = Color.rfAdaptive(
        light: Color(red: 0.68, green: 0.34, blue: 0.19),
        dark: Color(red: 0.78, green: 0.48, blue: 0.30)
    )

    // MARK: - Fallbacks (Sicak tonlar, Claude-inspired)

    /// Primary renk — terracotta aksani.
    static let fallbackPrimary = Color.rfAdaptive(
        light: Color(red: 0.76, green: 0.37, blue: 0.24),
        dark: Color(red: 0.85, green: 0.47, blue: 0.30)
    )

    /// Arkaplan rengi — sicak krem (light), sicak koyu kahve (dark).
    static let fallbackBackground = Color.rfAdaptive(
        light: Color(red: 0.957, green: 0.953, blue: 0.933),
        dark: Color(red: 0.169, green: 0.165, blue: 0.153)
    )

    /// Yuzey rengi — hafif yukseltimlmis sicak yuzey.
    static let fallbackSurface = Color.rfAdaptive(
        light: Color(red: 0.975, green: 0.970, blue: 0.955),
        dark: Color(red: 0.200, green: 0.196, blue: 0.184)
    )

    /// Birincil metin rengi — sicak siyah (light), sicak beyaz (dark).
    static let fallbackTextPrimary = Color.rfAdaptive(
        light: Color(red: 0.102, green: 0.102, blue: 0.094),
        dark: Color(red: 0.933, green: 0.933, blue: 0.933)
    )

    /// Ikincil metin rengi — sicak gri.
    static let fallbackTextSecondary = Color.rfAdaptive(
        light: Color(red: 0.420, green: 0.416, blue: 0.408),
        dark: Color(red: 0.604, green: 0.596, blue: 0.576)
    )

    /// Ucuncul metin rengi — soluk sicak gri.
    static let fallbackTextTertiary = Color.rfAdaptive(
        light: Color(red: 0.56, green: 0.55, blue: 0.53),
        dark: Color(red: 0.46, green: 0.45, blue: 0.43)
    )

    // MARK: - Brand Gradients

    /// Marka gradyani — terracotta tonlari.
    static let brandGradient = LinearGradient(
        colors: [
            Color.rfAdaptive(light: Color(red: 0.76, green: 0.37, blue: 0.24),
                  dark: Color(red: 0.82, green: 0.44, blue: 0.28)),
            Color.rfAdaptive(light: Color(red: 0.68, green: 0.30, blue: 0.18),
                  dark: Color(red: 0.75, green: 0.38, blue: 0.22))
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    /// Aksan gradyani — sicak amber tonlari.
    static let accentGradient = LinearGradient(
        colors: [
            Color.rfAdaptive(light: Color(red: 0.72, green: 0.50, blue: 0.22),
                  dark: Color(red: 0.80, green: 0.58, blue: 0.30)),
            Color.rfAdaptive(light: Color(red: 0.60, green: 0.38, blue: 0.18),
                  dark: Color(red: 0.70, green: 0.48, blue: 0.24))
        ],
        startPoint: .leading,
        endPoint: .trailing
    )

    // MARK: - Hero / Background Gradients

    /// Hero arkaplan baslangic rengi — sicak tonlar.
    static let heroGradientStart = Color.rfAdaptive(
        light: Color(red: 0.96, green: 0.94, blue: 0.91),
        dark: Color(red: 0.22, green: 0.20, blue: 0.17)
    )

    /// Hero arkaplan bitis rengi.
    static let heroGradientEnd = Color.rfAdaptive(
        light: Color(red: 0.957, green: 0.953, blue: 0.933),
        dark: Color(red: 0.169, green: 0.165, blue: 0.153)
    )

    // MARK: - Elevated Surface

    /// Glass kart arkaplan rengi.
    static let elevatedSurface = Color.rfAdaptive(
        light: Color.white.opacity(0.7),
        dark: Color.white.opacity(0.06)
    )

    // MARK: - Chat Bubble (Claude-inspired, sicak tonlar)

    /// AI mesaj baloncugu arka plan rengi — cok hafif, neredeyse saydam.
    static let aiBubble = Color.rfAdaptive(
        light: Color(red: 0.97, green: 0.96, blue: 0.94),
        dark: Color(red: 0.20, green: 0.19, blue: 0.18)
    )

    /// Kullanici mesaj baloncugu arka plan rengi — sicak tan.
    static let userBubble = Color.rfAdaptive(
        light: Color(red: 0.867, green: 0.851, blue: 0.808),
        dark: Color(red: 0.224, green: 0.224, blue: 0.216)
    )

    /// Kullanici baloncugu gradient baslangic.
    static let userBubbleGradientStart = Color.rfAdaptive(
        light: Color(red: 0.88, green: 0.86, blue: 0.82),
        dark: Color(red: 0.24, green: 0.23, blue: 0.22)
    )

    /// Kullanici baloncugu gradient bitis.
    static let userBubbleGradientEnd = Color.rfAdaptive(
        light: Color(red: 0.84, green: 0.82, blue: 0.78),
        dark: Color(red: 0.21, green: 0.20, blue: 0.19)
    )

    // MARK: - Divider

    /// Ayirici cizgi rengi (dark mode uyumlu).
    static let divider = Color.rfAdaptive(
        light: Color(red: 0.85, green: 0.84, blue: 0.82),
        dark: Color(red: 0.28, green: 0.27, blue: 0.26)
    )
}

// MARK: - Color Extension for Dark Mode

extension Color {
    /// Light ve dark mode icin farkli renkler tanimlar.
    /// MarkdownUI ile cakismayi onlemek icin `rfAdaptive` kullanilir.
    static func rfAdaptive(light: Color, dark: Color) -> Color {
        Color(uiColor: UIColor { traitCollection in
            switch traitCollection.userInterfaceStyle {
            case .dark:
                return UIColor(dark)
            default:
                return UIColor(light)
            }
        })
    }
}
