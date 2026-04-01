import SwiftUI

/// Chat mesaj girdi cubugu — Claude Code'dan ilham alan profesyonel tasarim.
/// Cok satirli giriş, Claude calısırken durdurma butonu, komut paleti entegrasyonu.
struct RFChatInput: View {
    @Binding var text: String
    let isEnabled: Bool
    let isSending: Bool
    let isProcessing: Bool  // Claude aktif olarak yanıt uretirken true
    let isRecording: Bool
    let audioLevel: Float
    let onSend: () -> Void
    let onStop: () -> Void   // aktif stream'i iptal et
    let onMicTap: () -> Void
    let onMicLongPress: () -> Void

    @FocusState private var isFocused: Bool

    init(
        text: Binding<String>,
        isEnabled: Bool = true,
        isSending: Bool = false,
        isProcessing: Bool = false,
        isRecording: Bool = false,
        audioLevel: Float = 0,
        onSend: @escaping () -> Void,
        onStop: @escaping () -> Void = {},
        onMicTap: @escaping () -> Void = {},
        onMicLongPress: @escaping () -> Void = {}
    ) {
        self._text = text
        self.isEnabled = isEnabled
        self.isSending = isSending
        self.isProcessing = isProcessing
        self.isRecording = isRecording
        self.audioLevel = audioLevel
        self.onSend = onSend
        self.onStop = onStop
        self.onMicTap = onMicTap
        self.onMicLongPress = onMicLongPress
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .bottom, spacing: RFSpacing.sm) {
                // + attachment placeholder
                Button { } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(RFColors.fallbackTextSecondary)
                        .frame(width: 34, height: 34)
                        .background(RFColors.fallbackSurface)
                        .clipShape(Circle())
                        .overlay(Circle().stroke(RFColors.divider, lineWidth: 0.5))
                }
                .buttonStyle(.plain)
                .disabled(isProcessing)

                HStack(alignment: .bottom, spacing: RFSpacing.xs) {
                    multiLineTextField
                    actionButton
                }
                .padding(.horizontal, RFSpacing.sm)
                .padding(.vertical, RFSpacing.xs)
                .background(
                    RoundedRectangle(cornerRadius: RFCornerRadius.extraLarge)
                        .fill(RFColors.fallbackSurface)
                        .shadow(color: Color.black.opacity(0.08), radius: 10, x: 0, y: -2)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: RFCornerRadius.extraLarge)
                        .stroke(
                            isFocused ? RFColors.fallbackPrimary.opacity(0.3) : RFColors.divider.opacity(0.6),
                            lineWidth: isFocused ? 1.5 : 0.5
                        )
                )
                .animation(RFAnimation.springSnappy, value: isFocused)
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.top, RFSpacing.sm)
            .padding(.bottom, RFSpacing.xs)
        }
        .background(RFColors.fallbackBackground.ignoresSafeArea(edges: .bottom))
    }

    // MARK: - Multi-line TextField

    private var multiLineTextField: some View {
        TextField(
            String(localized: "chat.input.placeholder"),
            text: $text,
            axis: .vertical
        )
        .font(RFTypography.body)
        .foregroundStyle(RFColors.fallbackTextPrimary)
        .lineLimit(1...6)
        .focused($isFocused)
        .disabled(!isEnabled || isRecording || isProcessing)
        .padding(.horizontal, RFSpacing.xs)
        .padding(.vertical, RFSpacing.xs)
    }

    // MARK: - Action Button

    /// Claude işlenirken: durdur butonu.
    /// Metin varsa: gönder butonu.
    /// Metin yoksa: mikrofon butonu.
    @ViewBuilder
    private var actionButton: some View {
        if isProcessing {
            stopButton
        } else if hasText || isSending {
            sendButton
        } else {
            micButton
        }
    }

    private var stopButton: some View {
        Button {
            RFHaptics.impact(.rigid)
            onStop()
        } label: {
            Image(systemName: "stop.fill")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: 36, height: 36)
                .background(RFColors.error)
                .clipShape(Circle())
        }
        .buttonStyle(RFPressButtonStyle())
        .transition(.scale.combined(with: .opacity))
        .animation(RFAnimation.springSnappy, value: isProcessing)
    }

    private var micButton: some View {
        ZStack {
            if isRecording {
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
    VStack(spacing: 0) {
        Spacer()
        RFChatInput(
            text: .constant("Merhaba, projemin durumunu kontrol eder misin?"),
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
            isProcessing: true,
            onSend: {},
            onStop: {},
            onMicTap: {}
        )
        RFChatInput(
            text: .constant(""),
            isRecording: true,
            audioLevel: 0.6,
            onSend: {},
            onMicTap: {}
        )
    }
    .background(RFColors.fallbackBackground)
}
