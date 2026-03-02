import SwiftUI

/// RafRaf renk paleti.
/// Tum renkler buradan tanimlanir, feature ekranlarinda dogrudan Color literal YASAK.
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

    // MARK: - Semantic

    static let success = Color.green
    static let warning = Color.orange
    static let error = Color.red
    static let info = Color.blue

    // MARK: - Fallbacks (Asset catalog olmadan kullanilabilir)

    static let fallbackPrimary = Color.blue
    static let fallbackBackground = Color(.systemBackground)
    static let fallbackSurface = Color(.secondarySystemBackground)
    static let fallbackTextPrimary = Color(.label)
    static let fallbackTextSecondary = Color(.secondaryLabel)
}
