import SwiftUI

/// Chat mesaj girdi cubugu — Claude-inspired temiz gorunum.
/// Sicak yuzey arkaplan ve terracotta gonder butonu.
struct RFChatInput: View {
    @Binding var text: String
    let isEnabled: Bool
    let isSending: Bool
    let onSend: () -> Void

    init(
        text: Binding<String>,
        isEnabled: Bool = true,
        isSending: Bool = false,
        onSend: @escaping () -> Void
    ) {
        self._text = text
        self.isEnabled = isEnabled
        self.isSending = isSending
        self.onSend = onSend
    }

    var body: some View {
        HStack(alignment: .bottom, spacing: RFSpacing.xs) {
            textField
            sendButton
        }
        .padding(.horizontal, RFSpacing.md)
        .padding(.vertical, RFSpacing.sm)
        .background(RFColors.fallbackSurface)
        .overlay(alignment: .top) {
            RFColors.divider.frame(height: 0.5)
        }
    }

    // MARK: - Subviews

    private var textField: some View {
        RFTextField(
            String(localized: "chat.input.placeholder"),
            text: $text
        )
        .disabled(!isEnabled)
    }

    private var sendButton: some View {
        Button {
            RFHaptics.impact(.medium)
            onSend()
        } label: {
            Group {
                if isSending {
                    ProgressView()
                        .tint(.white)
                } else {
                    Image(systemName: "arrow.up")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(.white)
                }
            }
            .frame(width: 36, height: 36)
            .background(
                canSend
                    ? AnyShapeStyle(RFColors.brandGradient)
                    : AnyShapeStyle(RFColors.fallbackTextTertiary.opacity(0.3))
            )
            .clipShape(Circle())
        }
        .disabled(!canSend)
        .buttonStyle(RFPressButtonStyle())
        .animation(RFAnimation.springSnappy, value: canSend)
    }

    // MARK: - Computed

    private var canSend: Bool {
        isEnabled && !isSending && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

#Preview {
    VStack {
        Spacer()
        RFChatInput(
            text: .constant("Merhaba"),
            onSend: {}
        )
        RFChatInput(
            text: .constant(""),
            onSend: {}
        )
        RFChatInput(
            text: .constant("Gonderiliyor..."),
            isSending: true,
            onSend: {}
        )
    }
    .background(RFColors.fallbackBackground)
}
