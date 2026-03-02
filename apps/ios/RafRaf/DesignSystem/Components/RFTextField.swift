import SwiftUI

/// RafRaf metin girisi bileseni.
/// Feature ekranlarinda raw SwiftUI `TextField` yerine bu bilesen kullanilir.
struct RFTextField: View {
    let placeholder: String
    @Binding var text: String
    let isSecure: Bool
    let errorMessage: String?

    init(
        _ placeholder: String,
        text: Binding<String>,
        isSecure: Bool = false,
        errorMessage: String? = nil
    ) {
        self.placeholder = placeholder
        self._text = text
        self.isSecure = isSecure
        self.errorMessage = errorMessage
    }

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
            Group {
                if isSecure {
                    SecureField(placeholder, text: $text)
                } else {
                    TextField(placeholder, text: $text)
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
            isSecure: true
        )

        RFTextField(
            "Hatali alan",
            text: .constant(""),
            errorMessage: "Bu alan zorunludur"
        )
    }
    .padding()
}
