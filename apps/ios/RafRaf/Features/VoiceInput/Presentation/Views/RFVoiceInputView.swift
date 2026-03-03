import SwiftUI

/// Sesli giris ana ekrani.
/// Mikrofon butonu, dalga formu, transkripsiyon gosterimi ve dil secimi icerir.
/// Chat ekraninin alt kismindan overlay olarak gosterilir.
struct RFVoiceInputView: View {
    @Bindable var viewModel: VoiceInputViewModel

    var body: some View {
        VStack(spacing: RFSpacing.md) {
            // Hata banner'i
            if let errorMessage = viewModel.errorMessage {
                RFErrorView(
                    message: errorMessage,
                    retryAction: {
                        viewModel.dismissError()
                    }
                )
                .transition(.move(edge: .top).combined(with: .opacity))
            }

            // Transkripsiyon overlay
            if viewModel.isRecording || viewModel.state == .processing {
                RFTranscriptionOverlay(
                    finalText: viewModel.finalTranscription,
                    interimText: viewModel.interimTranscription,
                    isProcessing: viewModel.state == .processing
                )
                .transition(.opacity)
            }

            // Waveform
            if viewModel.isRecording {
                RFWaveformView(
                    audioLevel: viewModel.audioLevel.normalizedLevel,
                    isActive: viewModel.isRecording
                )
                .padding(.horizontal, RFSpacing.xl)
                .transition(.opacity)
            }

            // Alt kontrol cubugu
            HStack(spacing: RFSpacing.md) {
                // Dil secimi (kayit yokken gosterilir)
                if !viewModel.isRecording && viewModel.state != .processing {
                    RFLanguageSelector(
                        selectedLanguage: Binding(
                            get: { viewModel.selectedLanguage },
                            set: { viewModel.changeLanguage($0) }
                        ),
                        onLanguageChanged: { language in
                            viewModel.changeLanguage(language)
                        }
                    )
                }

                Spacer()

                // Iptal butonu (kayit sirasinda)
                if viewModel.isRecording {
                    RFButton(
                        String(localized: "voiceInput.cancel"),
                        style: .ghost,
                        size: .small
                    ) {
                        Task {
                            await viewModel.cancelRecording()
                        }
                    }
                }

                // Mikrofon butonu
                RFVoiceInputButton(
                    isRecording: viewModel.isRecording,
                    isProcessing: viewModel.state == .processing || viewModel.state == .requesting,
                    audioLevel: viewModel.audioLevel.normalizedLevel,
                    onTap: {
                        Task {
                            if viewModel.isRecording {
                                await viewModel.stopRecording()
                            } else {
                                await viewModel.startRecording()
                            }
                        }
                    },
                    onLongPressStart: {
                        Task {
                            await viewModel.startRecording()
                        }
                    },
                    onLongPressEnd: {
                        Task {
                            await viewModel.stopRecording()
                        }
                    }
                )
            }
            .padding(.horizontal, RFSpacing.md)
        }
        .padding(.vertical, RFSpacing.sm)
        .animation(.easeInOut(duration: 0.2), value: viewModel.state)
    }
}

#Preview {
    @Previewable @State var mockViewModel: VoiceInputViewModel = {
        let repo = MockVoiceInputRepository()
        let audioManager = RFAudioSessionManager()
        return VoiceInputViewModel(
            startRecordingUseCase: StartVoiceRecordingUseCase(repository: repo),
            stopRecordingUseCase: StopVoiceRecordingUseCase(repository: repo),
            audioSessionManager: audioManager
        )
    }()

    VStack {
        Spacer()
        RFVoiceInputView(viewModel: mockViewModel)
    }
    .padding()
}

// MARK: - Preview Mock

/// Preview icin mock repository.
private final class MockVoiceInputRepository: VoiceInputRepositoryProtocol, @unchecked Sendable {
    var isConnected: Bool = false

    func startStreaming(language: VoiceLanguage) async throws -> AsyncStream<TranscriptionResult> {
        isConnected = true
        return AsyncStream { _ in }
    }

    func stopStreaming() async {
        isConnected = false
    }
}
