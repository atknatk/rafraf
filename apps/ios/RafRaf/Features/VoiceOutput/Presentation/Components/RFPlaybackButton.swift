import SwiftUI

/// Ses oynatma kontrol butonu.
/// Oynat/duraklat/durdur durumlarini gosterir.
struct RFPlaybackButton: View {
    let state: VoiceOutputState
    let onPlay: () -> Void
    let onPause: () -> Void
    let onResume: () -> Void
    let onStop: () -> Void

    var body: some View {
        HStack(spacing: RFSpacing.sm) {
            // Ana oynatma/duraklatma butonu
            Button(action: primaryAction) {
                ZStack {
                    Circle()
                        .fill(RFColors.fallbackPrimary)
                        .frame(width: 44, height: 44)

                    if isLoading {
                        ProgressView()
                            .tint(.white)
                    } else {
                        Image(systemName: primaryIconName)
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(.white)
                    }
                }
            }
            .disabled(isLoading)
            .accessibilityLabel(Text(primaryAccessibilityLabel))

            // Durdurma butonu (sadece oynatma/duraklatma durumunda)
            if isActive {
                Button(action: onStop) {
                    ZStack {
                        Circle()
                            .fill(RFColors.fallbackSurface)
                            .frame(width: 36, height: 36)

                        Image(systemName: "stop.fill")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(RFColors.fallbackTextPrimary)
                    }
                }
                .accessibilityLabel(Text(String(localized: "voiceOutput.button.stop")))
            }
        }
    }

    // MARK: - Computed

    private var isLoading: Bool {
        state == .loading
    }

    private var isActive: Bool {
        state == .playing || state == .paused
    }

    private var primaryIconName: String {
        switch state {
        case .idle, .error:
            return "speaker.wave.2.fill"
        case .loading:
            return "speaker.wave.2.fill"
        case .playing:
            return "pause.fill"
        case .paused:
            return "play.fill"
        }
    }

    private var primaryAccessibilityLabel: String {
        switch state {
        case .idle, .error:
            return String(localized: "voiceOutput.button.play")
        case .loading:
            return String(localized: "voiceOutput.button.loading")
        case .playing:
            return String(localized: "voiceOutput.button.pause")
        case .paused:
            return String(localized: "voiceOutput.button.resume")
        }
    }

    private func primaryAction() {
        switch state {
        case .idle, .error:
            onPlay()
        case .playing:
            onPause()
        case .paused:
            onResume()
        case .loading:
            break
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.lg) {
        RFPlaybackButton(
            state: .idle,
            onPlay: {}, onPause: {}, onResume: {}, onStop: {}
        )
        RFPlaybackButton(
            state: .loading,
            onPlay: {}, onPause: {}, onResume: {}, onStop: {}
        )
        RFPlaybackButton(
            state: .playing,
            onPlay: {}, onPause: {}, onResume: {}, onStop: {}
        )
        RFPlaybackButton(
            state: .paused,
            onPlay: {}, onPause: {}, onResume: {}, onStop: {}
        )
    }
    .padding()
}
