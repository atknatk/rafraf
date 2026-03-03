import SwiftUI

/// Mikrofon butonu.
/// Push-to-talk (basili tutma) ve toggle (dokunma) modlarini destekler.
struct RFVoiceInputButton: View {
    let isRecording: Bool
    let isProcessing: Bool
    let audioLevel: Float
    let onTap: () -> Void
    let onLongPressStart: () -> Void
    let onLongPressEnd: () -> Void

    @State private var isPressed: Bool = false

    var body: some View {
        ZStack {
            // Ses seviyesi halkasi
            if isRecording {
                Circle()
                    .stroke(RFColors.error.opacity(0.3), lineWidth: 3)
                    .frame(width: buttonSize + pulseSize, height: buttonSize + pulseSize)
                    .scaleEffect(1.0 + CGFloat(audioLevel) * 0.3)
                    .animation(.easeInOut(duration: 0.1), value: audioLevel)
            }

            // Ana buton
            Circle()
                .fill(buttonColor)
                .frame(width: buttonSize, height: buttonSize)
                .overlay {
                    if isProcessing {
                        ProgressView()
                            .tint(.white)
                    } else {
                        Image(systemName: isRecording ? "stop.fill" : "mic.fill")
                            .font(.system(size: iconSize, weight: .semibold))
                            .foregroundStyle(.white)
                    }
                }
                .shadow(color: buttonColor.opacity(0.4), radius: isRecording ? 8 : 4, y: 2)
                .scaleEffect(isPressed ? 0.9 : 1.0)
                .animation(.easeInOut(duration: 0.15), value: isPressed)
        }
        .simultaneousGesture(
            LongPressGesture(minimumDuration: 0.3)
                .onChanged { _ in
                    isPressed = true
                    onLongPressStart()
                }
                .sequenced(before: DragGesture(minimumDistance: 0)
                    .onEnded { _ in
                        isPressed = false
                        onLongPressEnd()
                    }
                )
        )
        .simultaneousGesture(
            TapGesture()
                .onEnded {
                    onTap()
                }
        )
        .accessibilityLabel(accessibilityText)
        .accessibilityHint(String(localized: "voiceInput.button.hint"))
        .accessibilityAddTraits(.isButton)
    }

    // MARK: - Private

    private var buttonSize: CGFloat { 56 }
    private var iconSize: CGFloat { 22 }
    private var pulseSize: CGFloat { 16 }

    private var buttonColor: Color {
        if isRecording {
            return RFColors.error
        }
        return RFColors.fallbackPrimary
    }

    private var accessibilityText: String {
        if isRecording {
            return String(localized: "voiceInput.button.stopRecording")
        }
        return String(localized: "voiceInput.button.startRecording")
    }
}

#Preview {
    VStack(spacing: RFSpacing.xl) {
        RFVoiceInputButton(
            isRecording: false,
            isProcessing: false,
            audioLevel: 0,
            onTap: {},
            onLongPressStart: {},
            onLongPressEnd: {}
        )

        RFVoiceInputButton(
            isRecording: true,
            isProcessing: false,
            audioLevel: 0.6,
            onTap: {},
            onLongPressStart: {},
            onLongPressEnd: {}
        )

        RFVoiceInputButton(
            isRecording: false,
            isProcessing: true,
            audioLevel: 0,
            onTap: {},
            onLongPressStart: {},
            onLongPressEnd: {}
        )
    }
    .padding()
}
