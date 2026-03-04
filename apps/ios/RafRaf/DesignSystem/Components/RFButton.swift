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

/// Press-scale animasyonu icin ozel buton stili.
struct RFPressButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
            .animation(RFAnimation.springSnappy, value: configuration.isPressed)
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
    let systemImage: String?
    let action: () -> Void

    init(
        _ title: String,
        style: RFButtonStyle = .primary,
        size: RFButtonSize = .medium,
        isLoading: Bool = false,
        isDisabled: Bool = false,
        systemImage: String? = nil,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.style = style
        self.size = size
        self.isLoading = isLoading
        self.isDisabled = isDisabled
        self.systemImage = systemImage
        self.action = action
    }

    var body: some View {
        Button {
            RFHaptics.impact(.light)
            action()
        } label: {
            HStack(spacing: RFSpacing.xs) {
                if isLoading {
                    ProgressView()
                        .tint(foregroundColor)
                } else if let systemImage {
                    Image(systemName: systemImage)
                        .font(size.font)
                        .foregroundStyle(foregroundColor)
                }

                Text(title)
                    .font(size.font)
                    .foregroundStyle(foregroundColor)
            }
            .frame(maxWidth: style == .ghost ? nil : .infinity)
            .padding(.vertical, size.verticalPadding)
            .padding(.horizontal, size.horizontalPadding)
            .background {
                Group {
                    if style == .primary {
                        RFColors.brandGradient
                    } else {
                        backgroundColor
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))
            .overlay {
                if style == .outline {
                    RoundedRectangle(cornerRadius: RFCornerRadius.medium)
                        .strokeBorder(RFColors.fallbackPrimary, lineWidth: 1.5)
                }
            }
            .rfElevation(style == .primary ? .low : .low)
        }
        .buttonStyle(RFPressButtonStyle())
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
        RFButton("With Icon", style: .primary, systemImage: "arrow.right") {}
        RFButton("Secondary Button", style: .secondary) {}
        RFButton("Outline Button", style: .outline) {}
        RFButton("Ghost Button", style: .ghost) {}
        RFButton("Destructive Button", style: .destructive) {}
        RFButton("Loading Button", isLoading: true) {}
        RFButton("Disabled Button", isDisabled: true) {}
    }
    .padding()
}
