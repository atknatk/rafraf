import SwiftUI

/// Chat mesaj girdi cubugu.
/// Metin girisi, gonder butonu ve ek butonu icerir.
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
        VStack(spacing: 0) {
            Divider()
                .foregroundStyle(RFColors.divider)

            HStack(alignment: .bottom, spacing: RFSpacing.xs) {
                textField

                sendButton
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
            .background(RFColors.fallbackBackground)
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
        RFButton(
            String(localized: "chat.send"),
            style: .primary,
            size: .small,
            isLoading: isSending,
            isDisabled: !canSend
        ) {
            onSend()
        }
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
}
