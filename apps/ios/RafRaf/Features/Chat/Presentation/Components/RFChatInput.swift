import SwiftUI

/// Chat mesaj girdi cubugu — Claude-inspired temiz gorunum.
/// Sicak yuzey arkaplan, mikrofon butonu ve terracotta gonder butonu.
struct RFChatInput: View {
    @Binding var text: String
    let isEnabled: Bool
    let isSending: Bool
    let isRecording: Bool
    let audioLevel: Float
    let onSend: () -> Void
    let onMicTap: () -> Void
    let onMicLongPress: () -> Void

    init(
        text: Binding<String>,
        isEnabled: Bool = true,
        isSending: Bool = false,
        isRecording: Bool = false,
        audioLevel: Float = 0,
        onSend: @escaping () -> Void,
        onMicTap: @escaping () -> Void = {},
        onMicLongPress: @escaping () -> Void = {}
    ) {
        self._text = text
        self.isEnabled = isEnabled
        self.isSending = isSending
        self.isRecording = isRecording
        self.audioLevel = audioLevel
        self.onSend = onSend
        self.onMicTap = onMicTap
        self.onMicLongPress = onMicLongPress
    }

    var body: some View {
        HStack(alignment: .bottom, spacing: RFSpacing.xs) {
            textField
            actionButton
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
        .disabled(!isEnabled || isRecording)
    }

    /// Metin bos ve gonderim yokken mikrofon, aksi halde gonder butonu gosterir.
    @ViewBuilder
    private var actionButton: some View {
        if hasText || isSending {
            sendButton
        } else {
            micButton
        }
    }

    private var micButton: some View {
        ZStack {
            if isRecording {
                // Pulse ring — ses seviyesine gore buyur
                Circle()
                    .stroke(RFColors.error.opacity(0.4), lineWidth: 2)
                    .scaleEffect(1.0 + CGFloat(audioLevel) * 0.3)
                    .animation(RFAnimation.springSnappy, value: audioLevel)

                Image(systemName: "stop.fill")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white)
            } else {
                Image(systemName: "mic.fill")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.white)
            }
        }
        .frame(width: 36, height: 36)
        .background(isRecording ? RFColors.error : RFColors.fallbackPrimary)
        .clipShape(Circle())
        .onTapGesture {
            RFHaptics.impact(.medium)
            onMicTap()
        }
        .onLongPressGesture(minimumDuration: 0.5) {
            RFHaptics.impact(.heavy)
            onMicLongPress()
        }
        .disabled(!isEnabled)
        .animation(RFAnimation.springSnappy, value: isRecording)
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

    private var hasText: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var canSend: Bool {
        isEnabled && !isSending && hasText
    }
}

#Preview {
    VStack {
        Spacer()
        RFChatInput(
            text: .constant("Merhaba"),
            onSend: {},
            onMicTap: {}
        )
        RFChatInput(
            text: .constant(""),
            onSend: {},
            onMicTap: {}
        )
        RFChatInput(
            text: .constant(""),
            isRecording: true,
            audioLevel: 0.6,
            onSend: {},
            onMicTap: {}
        )
        RFChatInput(
            text: .constant("Gonderiliyor..."),
            isSending: true,
            onSend: {},
            onMicTap: {}
        )
    }
    .background(RFColors.fallbackBackground)
}
