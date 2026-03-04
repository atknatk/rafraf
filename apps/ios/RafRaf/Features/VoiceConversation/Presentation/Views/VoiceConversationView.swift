import SwiftUI

/// ChatGPT benzeri tam ekran sesli konusma ekrani.
/// Kullanici konusur → sessizlik → otomatik gonderim → AI cevap text + ses → tekrar dinleme.
struct VoiceConversationView: View {
    @Bindable var viewModel: VoiceConversationViewModel
    let onDismiss: () -> Void

    var body: some View {
        ZStack {
            // Arkaplan
            RFColors.fallbackBackground
                .ignoresSafeArea()

            VStack(spacing: 0) {
                topBar
                Spacer()
                centerContent
                Spacer()
                bottomContent
            }
            .padding(RFSpacing.md)
        }
        .overlay {
            if let error = viewModel.errorMessage {
                errorBanner(error)
            }
        }
    }

    // MARK: - Top Bar

    private var topBar: some View {
        HStack {
            languageSelector

            Spacer()

            Button {
                Task { await viewModel.exitVoiceMode() }
                onDismiss()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.title2)
                    .foregroundStyle(RFColors.fallbackTextSecondary)
            }
        }
    }

    private var languageSelector: some View {
        Menu {
            ForEach(VoiceLanguage.allCases, id: \.self) { language in
                Button {
                    viewModel.changeLanguage(language)
                } label: {
                    HStack {
                        Text(language.displayName)
                        if language == viewModel.selectedLanguage {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
        } label: {
            HStack(spacing: RFSpacing.xxs) {
                Image(systemName: "globe")
                RFText(
                    viewModel.selectedLanguage.displayName,
                    style: .caption,
                    color: RFColors.fallbackTextSecondary
                )
            }
            .padding(.horizontal, RFSpacing.sm)
            .padding(.vertical, RFSpacing.xxs)
            .background(RFColors.fallbackSurface)
            .clipShape(Capsule())
        }
    }

    // MARK: - Center Content

    @ViewBuilder
    private var centerContent: some View {
        switch viewModel.state {
        case .idle:
            idleView
        case .listening:
            listeningView
        case .processing:
            processingView
        case .aiSpeaking:
            aiSpeakingView
        case .interrupted:
            interruptedView
        }
    }

    private var idleView: some View {
        VStack(spacing: RFSpacing.lg) {
            pulsingOrb(color: RFColors.fallbackTextSecondary.opacity(0.3), size: 100)
            RFText(
                String(localized: "voice.idle.hint"),
                style: .body,
                color: RFColors.fallbackTextSecondary
            )
            .multilineTextAlignment(.center)
        }
    }

    private var listeningView: some View {
        VStack(spacing: RFSpacing.lg) {
            // Ses seviyesine gore buyuyen/kucuken orb
            pulsingOrb(
                color: RFColors.primary.opacity(Double(0.3 + viewModel.audioLevel * 0.7)),
                size: CGFloat(80 + viewModel.audioLevel * 60)
            )

            // Canli transkripsiyon
            VStack(spacing: RFSpacing.xs) {
                if !viewModel.transcription.isEmpty {
                    RFText(
                        viewModel.transcription,
                        style: .body,
                        color: RFColors.fallbackTextPrimary
                    )
                    .multilineTextAlignment(.center)
                }

                if !viewModel.interimText.isEmpty {
                    RFText(
                        viewModel.interimText,
                        style: .body,
                        color: RFColors.fallbackTextSecondary.opacity(0.6)
                    )
                    .multilineTextAlignment(.center)
                }
            }
            .padding(.horizontal, RFSpacing.lg)
            .animation(RFAnimation.springGentle, value: viewModel.transcription)
        }
    }

    private var processingView: some View {
        VStack(spacing: RFSpacing.lg) {
            pulsingOrb(color: RFColors.accent.opacity(0.5), size: 80)
                .overlay {
                    ProgressView()
                        .tint(RFColors.fallbackTextPrimary)
                }
            RFText(
                String(localized: "voice.processing"),
                style: .body,
                color: RFColors.fallbackTextSecondary
            )
        }
    }

    private var aiSpeakingView: some View {
        VStack(spacing: RFSpacing.lg) {
            // AI konusuyor animasyonu
            speakingOrb
                .onTapGesture {
                    Task { await viewModel.handleBargeIn() }
                }

            // Streaming text
            ScrollView {
                RFText(
                    viewModel.aiResponseText,
                    style: .body,
                    color: RFColors.fallbackTextPrimary
                )
                .multilineTextAlignment(.center)
                .animation(.easeInOut(duration: 0.05), value: viewModel.aiResponseText)
            }
            .frame(maxHeight: 200)
            .padding(.horizontal, RFSpacing.lg)

            RFText(
                String(localized: "voice.tapToInterrupt"),
                style: .caption,
                color: RFColors.fallbackTextSecondary.opacity(0.6)
            )
        }
    }

    private var interruptedView: some View {
        VStack(spacing: RFSpacing.md) {
            pulsingOrb(color: RFColors.warning.opacity(0.4), size: 80)
            RFText(
                String(localized: "voice.interrupted"),
                style: .caption,
                color: RFColors.fallbackTextSecondary
            )
        }
    }

    // MARK: - Bottom Content

    private var bottomContent: some View {
        VStack(spacing: RFSpacing.sm) {
            // Durum gostergesi
            stateIndicator
        }
    }

    private var stateIndicator: some View {
        HStack(spacing: RFSpacing.xs) {
            Circle()
                .fill(stateColor)
                .frame(width: 8, height: 8)
            RFText(stateText, style: .caption, color: RFColors.fallbackTextSecondary)
        }
    }

    private var stateColor: Color {
        switch viewModel.state {
        case .idle: RFColors.fallbackTextSecondary
        case .listening: RFColors.primary
        case .processing: RFColors.accent
        case .aiSpeaking: RFColors.success
        case .interrupted: RFColors.warning
        }
    }

    private var stateText: String {
        switch viewModel.state {
        case .idle: String(localized: "voice.state.idle")
        case .listening: String(localized: "voice.state.listening")
        case .processing: String(localized: "voice.state.processing")
        case .aiSpeaking: String(localized: "voice.state.aiSpeaking")
        case .interrupted: String(localized: "voice.state.interrupted")
        }
    }

    // MARK: - Components

    private func pulsingOrb(color: Color, size: CGFloat) -> some View {
        Circle()
            .fill(color)
            .frame(width: size, height: size)
            .shadow(color: color.opacity(0.4), radius: size / 4)
            .animation(RFAnimation.springGentle, value: size)
    }

    private var speakingOrb: some View {
        ZStack {
            // Dis halka — nefes alan animasyon
            Circle()
                .stroke(RFColors.primary.opacity(0.2), lineWidth: 3)
                .frame(width: 120, height: 120)
                .scaleEffect(1.1)
                .animation(
                    .easeInOut(duration: 1.0).repeatForever(autoreverses: true),
                    value: viewModel.state
                )

            // Orta orb
            Circle()
                .fill(RFColors.primary.opacity(0.5))
                .frame(width: 90, height: 90)
                .shadow(color: RFColors.primary.opacity(0.3), radius: 20)

            // Ikon
            Image(systemName: "waveform")
                .font(.title)
                .foregroundStyle(RFColors.fallbackTextPrimary)
        }
    }

    // MARK: - Error

    private func errorBanner(_ message: String) -> some View {
        VStack {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.white)
                RFText(message, style: .caption, color: .white)
                Spacer()
                Button {
                    viewModel.errorMessage = nil
                } label: {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white.opacity(0.8))
                }
            }
            .padding(RFSpacing.sm)
            .background(RFColors.error.opacity(0.9))
            .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))
            .padding(.horizontal, RFSpacing.md)
            .padding(.top, RFSpacing.xs)

            Spacer()
        }
    }
}

#Preview {
    VoiceConversationView(
        viewModel: {
            let vm = VoiceConversationViewModel(
                voiceInputVM: Container.shared.voiceInputViewModel(),
                webSocketManager: Container.shared.webSocketConnectionManager(),
                streamingAudioPlayer: StreamingAudioPlayer(),
                chatViewModel: Container.shared.chatViewModel()
            )
            return vm
        }(),
        onDismiss: {}
    )
}
