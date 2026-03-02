import SwiftUI

/// RafRaf metin stilleri.
enum RFTextStyle: Sendable {
    case largeTitle
    case title
    case subtitle
    case body
    case bodyBold
    case caption
    case captionBold

    var font: Font {
        switch self {
        case .largeTitle: return RFTypography.largeTitle
        case .title: return RFTypography.title
        case .subtitle: return RFTypography.subtitle
        case .body: return RFTypography.body
        case .bodyBold: return RFTypography.bodyBold
        case .caption: return RFTypography.caption
        case .captionBold: return RFTypography.captionBold
        }
    }

    var color: Color {
        switch self {
        case .largeTitle, .title, .subtitle, .bodyBold:
            return RFColors.fallbackTextPrimary
        case .body:
            return RFColors.fallbackTextPrimary
        case .caption, .captionBold:
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
        RFText("Large Title", style: .largeTitle)
        RFText("Title", style: .title)
        RFText("Subtitle", style: .subtitle)
        RFText("Body text", style: .body)
        RFText("Body bold", style: .bodyBold)
        RFText("Caption text", style: .caption)
        RFText("Caption bold", style: .captionBold)
        RFText("Custom color", style: .body, color: .red)
    }
    .padding()
}
