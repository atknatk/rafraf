import SwiftUI

/// RafRaf metin stilleri.
enum RFTextStyle: Sendable {
    case display
    case largeTitle
    case title
    case subtitle
    case headline
    case body
    case bodyLarge
    case bodyBold
    case caption
    case captionBold
    case overline

    var font: Font {
        switch self {
        case .display: return RFTypography.display
        case .largeTitle: return RFTypography.largeTitle
        case .title: return RFTypography.title
        case .subtitle: return RFTypography.subtitle
        case .headline: return RFTypography.headline
        case .body: return RFTypography.body
        case .bodyLarge: return RFTypography.bodyLarge
        case .bodyBold: return RFTypography.bodyBold
        case .caption: return RFTypography.caption
        case .captionBold: return RFTypography.captionBold
        case .overline: return RFTypography.overline
        }
    }

    var color: Color {
        switch self {
        case .display, .largeTitle, .title, .subtitle, .headline, .bodyBold:
            return RFColors.fallbackTextPrimary
        case .body, .bodyLarge:
            return RFColors.fallbackTextPrimary
        case .caption, .captionBold, .overline:
            return RFColors.fallbackTextSecondary
        }
    }
}

/// RafRaf tasarim sistemine uygun metin bileseni.
/// Feature ekranlarinda raw SwiftUI `Text` yerine bu bilesen kullanilir.
struct RFText: View {
    let content: String
    let style: RFTextStyle
    let color: Color?

    init(
        _ content: String,
        style: RFTextStyle = .body,
        color: Color? = nil
    ) {
        self.content = content
        self.style = style
        self.color = color
    }

    var body: some View {
        Text(content)
            .font(style.font)
            .foregroundStyle(color ?? style.color)
    }
}

#Preview {
    VStack(alignment: .leading, spacing: RFSpacing.sm) {
        RFText("Display", style: .display)
        RFText("Large Title", style: .largeTitle)
        RFText("Title", style: .title)
        RFText("Subtitle", style: .subtitle)
        RFText("Headline", style: .headline)
        RFText("Body Large", style: .bodyLarge)
        RFText("Body text", style: .body)
        RFText("Body bold", style: .bodyBold)
        RFText("Caption text", style: .caption)
        RFText("Caption bold", style: .captionBold)
        RFText("OVERLINE", style: .overline)
        RFText("Custom color", style: .body, color: .red)
    }
    .padding()
}
