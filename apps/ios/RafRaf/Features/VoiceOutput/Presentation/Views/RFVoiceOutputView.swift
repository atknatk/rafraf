import Factory
import SwiftUI

/// Ses cikis ayarlari ve kontrol gorunumu.
/// Chat ekraninda veya ayarlarda kullanilir.
struct RFVoiceOutputView: View {
    @Bindable var viewModel: VoiceOutputViewModel

    var body: some View {
        VStack(spacing: RFSpacing.md) {
            // Baslik
            HStack {
                RFText(
                    String(localized: "voiceOutput.title"),
                    style: .subtitle
                )
                Spacer()

                // Auto-play toggle
                Toggle(isOn: $viewModel.autoPlayEnabled) {
                    RFText(
                        String(localized: "voiceOutput.autoPlay"),
                        style: .caption
                    )
                }
                .toggleStyle(.switch)
                .tint(RFColors.fallbackPrimary)
            }

            // Ses secimi
            RFVoiceSelector(selectedVoice: $viewModel.selectedVoice)

            // Hiz ayari
            RFSpeedControl(speed: $viewModel.playbackSpeed)

            // Ilerleme cubugu
            RFPlaybackProgressBar(
                progress: viewModel.playbackProgress,
                isActive: viewModel.isPlaying || viewModel.isPaused
            )

            // Hata mesaji
            if let errorMessage = viewModel.errorMessage {
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(RFColors.error)

                    RFText(errorMessage, style: .caption)
                        .foregroundStyle(RFColors.error)

                    Spacer()

                    Button {
                        viewModel.dismissError()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(RFColors.fallbackTextTertiary)
                    }
                }
                .padding(RFSpacing.sm)
                .background(RFColors.error.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
        }
        .padding(RFSpacing.md)
    }
}

#Preview {
    let repo = Container.shared.voiceOutputRepository()
    let player = VoiceAudioPlayer()
    let vm = VoiceOutputViewModel(
        synthesizeSpeechUseCase: SynthesizeSpeechUseCase(repository: repo),
        audioPlayer: player
    )
    return RFVoiceOutputView(viewModel: vm)
}
