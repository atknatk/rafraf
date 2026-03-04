import SwiftUI

/// RafRaf metin girisi modlari.
enum RFTextFieldMode: Sendable {
    /// Tek satirli metin girisi.
    case text
    /// Sifre girisi (gizli metin).
    case secure
    /// Cok satirli metin girisi.
    case multiline
}

/// RafRaf metin girisi bileseni.
/// Feature ekranlarinda raw SwiftUI `TextField` yerine bu bilesen kullanilir.
struct RFTextField: View {
    let placeholder: String
    @Binding var text: String
    let mode: RFTextFieldMode
    let errorMessage: String?
    let lineLimit: ClosedRange<Int>
    let leadingIcon: String?

    @FocusState private var isFocused: Bool

    init(
        _ placeholder: String,
        text: Binding<String>,
        mode: RFTextFieldMode = .text,
        errorMessage: String? = nil,
        lineLimit: ClosedRange<Int> = 3...6,
        leadingIcon: String? = nil
    ) {
        self.placeholder = placeholder
        self._text = text
        self.mode = mode
        self.errorMessage = errorMessage
        self.lineLimit = lineLimit
        self.leadingIcon = leadingIcon
    }

    /// Backward-compatible init for isSecure parameter.
    init(
        _ placeholder: String,
        text: Binding<String>,
        isSecure: Bool,
        errorMessage: String? = nil
    ) {
        self.placeholder = placeholder
        self._text = text
        self.mode = isSecure ? .secure : .text
        self.errorMessage = errorMessage
        self.lineLimit = 3...6
        self.leadingIcon = nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
            HStack(spacing: RFSpacing.xs) {
                if let leadingIcon {
                    Image(systemName: leadingIcon)
                        .font(.body)
                        .foregroundStyle(
                            isFocused
                                ? RFColors.fallbackPrimary
                                : RFColors.fallbackTextTertiary
                        )
                        .animation(RFAnimation.easeDefault, value: isFocused)
                }

                Group {
                    switch mode {
                    case .text:
                        TextField(placeholder, text: $text)
                    case .secure:
                        SecureField(placeholder, text: $text)
                    case .multiline:
                        TextField(placeholder, text: $text, axis: .vertical)
                            .lineLimit(lineLimit)
                    }
                }
                .font(RFTypography.body)
                .focused($isFocused)
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
            .background(RFColors.fallbackSurface)
            .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))
            .overlay {
                RoundedRectangle(cornerRadius: RFCornerRadius.medium)
                    .strokeBorder(
                        borderColor,
                        lineWidth: isFocused ? 1.5 : 1
                    )
            }
            .animation(RFAnimation.easeDefault, value: isFocused)

            if let errorMessage {
                RFText(errorMessage, style: .caption, color: RFColors.error)
                    .padding(.horizontal, RFSpacing.xxs)
            }
        }
    }

    private var borderColor: Color {
        if errorMessage != nil {
            return RFColors.error
        }
        if isFocused {
            return RFColors.fallbackPrimary
        }
        return RFColors.divider.opacity(0.5)
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFTextField(
            "E-posta adresiniz",
            text: .constant(""),
            leadingIcon: "envelope"
        )

        RFTextField(
            "Sifreniz",
            text: .constant("password123"),
            mode: .secure,
            leadingIcon: "lock"
        )

        RFTextField(
            "Mesajiniz",
            text: .constant("Bu cok satirli bir metin girisi alanidir."),
            mode: .multiline
        )

        RFTextField(
            "Hatali alan",
            text: .constant(""),
            errorMessage: "Bu alan zorunludur"
        )
    }
    .padding()
}
