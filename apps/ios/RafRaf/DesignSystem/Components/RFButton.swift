import SwiftUI

/// RafRaf buton stilleri.
enum RFButtonStyle: Sendable {
    case primary
    case secondary
    case outline
    case ghost
    case destructive
}

/// RafRaf buton boyutlari.
enum RFButtonSize: Sendable {
    case small
    case medium
    case large

    var verticalPadding: CGFloat {
        switch self {
        case .small: return RFSpacing.xs
        case .medium: return RFSpacing.sm
        case .large: return RFSpacing.md
        }
    }

    var horizontalPadding: CGFloat {
        switch self {
        case .small: return RFSpacing.sm
        case .medium: return RFSpacing.md
        case .large: return RFSpacing.xl
        }
    }

    var font: Font {
        switch self {
        case .small: return RFTypography.caption
        case .medium: return RFTypography.button
        case .large: return RFTypography.button
        }
    }
}

/// RafRaf tasarim sistemine uygun buton bileseni.
/// Feature ekranlarinda raw SwiftUI `Button` yerine bu bilesen kullanilir.
struct RFButton: View {
    let title: String
    let style: RFButtonStyle
    let size: RFButtonSize
    let isLoading: Bool
    let isDisabled: Bool
    let action: () -> Void

    init(
        _ title: String,
        style: RFButtonStyle = .primary,
        size: RFButtonSize = .medium,
        isLoading: Bool = false,
        isDisabled: Bool = false,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.style = style
        self.size = size
        self.isLoading = isLoading
        self.isDisabled = isDisabled
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: RFSpacing.xs) {
                if isLoading {
                    ProgressView()
                        .tint(foregroundColor)
                }

                Text(title)
                    .font(size.font)
                    .foregroundStyle(foregroundColor)
            }
            .frame(maxWidth: style == .ghost ? nil : .infinity)
            .padding(.vertical, size.verticalPadding)
            .padding(.horizontal, size.horizontalPadding)
            .background(backgroundColor)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay {
                if style == .outline {
                    RoundedRectangle(cornerRadius: 12)
                        .strokeBorder(RFColors.fallbackPrimary, lineWidth: 1.5)
                }
            }
        }
        .disabled(isDisabled || isLoading)
        .opacity(isDisabled ? 0.5 : 1.0)
    }

    private var backgroundColor: Color {
        switch style {
        case .primary:
            return RFColors.fallbackPrimary
        case .secondary:
            return RFColors.fallbackSurface
        case .outline, .ghost:
            return .clear
        case .destructive:
            return RFColors.error
        }
    }

    private var foregroundColor: Color {
        switch style {
        case .primary, .destructive:
            return .white
        case .secondary:
            return RFColors.fallbackTextPrimary
        case .outline:
            return RFColors.fallbackPrimary
        case .ghost:
            return RFColors.fallbackPrimary
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFButton("Primary Button", style: .primary) {}
        RFButton("Secondary Button", style: .secondary) {}
        RFButton("Outline Button", style: .outline) {}
        RFButton("Ghost Button", style: .ghost) {}
        RFButton("Destructive Button", style: .destructive) {}
        RFButton("Loading Button", isLoading: true) {}
        RFButton("Disabled Button", isDisabled: true) {}
    }
    .padding()
}
