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

    init(
        _ placeholder: String,
        text: Binding<String>,
        mode: RFTextFieldMode = .text,
        errorMessage: String? = nil,
        lineLimit: ClosedRange<Int> = 3...6
    ) {
        self.placeholder = placeholder
        self._text = text
        self.mode = mode
        self.errorMessage = errorMessage
        self.lineLimit = lineLimit
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
    }

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
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
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
            .background(RFColors.fallbackSurface)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay {
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(
                        borderColor,
                        lineWidth: 1
                    )
            }

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
        return Color.clear
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFTextField(
            "E-posta adresiniz",
            text: .constant("")
        )

        RFTextField(
            "Sifreniz",
            text: .constant("password123"),
            mode: .secure
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
