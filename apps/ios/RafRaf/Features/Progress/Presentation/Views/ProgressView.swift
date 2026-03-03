import SwiftUI

/// AI islem ilerleme ekrani.
/// Genel ilerleme, step-by-step gosterge ve tool durumunu birlestirir.
struct ProgressContainerView: View {
    let viewModel: ProgressViewModel

    var body: some View {
        Group {
            if viewModel.isVisible, let state = viewModel.progressState {
                progressContent(state: state)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .animation(.spring(response: 0.4, dampingFraction: 0.8), value: viewModel.isVisible)
            }
        }
    }

    // MARK: - Private Views

    @ViewBuilder
    private func progressContent(state: ProgressState) -> some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                // Header
                progressHeader(state: state)

                // Progress bar
                RFProgressIndicator(
                    mode: state.mode,
                    progress: viewModel.progressFraction,
                    message: nil,
                    isCompact: false
                )

                // Step-by-step gosterge
                if !state.steps.isEmpty {
                    Divider()
                        .foregroundStyle(RFColors.divider)

                    RFStepProgressView(
                        steps: state.steps,
                        currentStepIndex: state.currentStepIndex
                    )
                }

                // Hata durumu
                if let errorMessage = viewModel.errorMessage {
                    errorBanner(message: errorMessage)
                }

                // Tamamlandi durumu
                if state.status == .completed {
                    completedBanner()
                }
            }
        }
        .padding(.horizontal, RFSpacing.md)
    }

    private func progressHeader(state: ProgressState) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                RFText(state.taskDescription, style: .bodyBold)

                if viewModel.isDeterminate {
                    RFText(
                        String(localized: "progress.step.count.\(viewModel.completedStepCount).\(viewModel.totalStepCount)"),
                        style: .caption,
                        color: RFColors.fallbackTextSecondary
                    )
                } else {
                    RFText(
                        String(localized: "progress.status.processing"),
                        style: .caption,
                        color: RFColors.fallbackTextSecondary
                    )
                }
            }

            Spacer()

            statusBadge(for: state.status)
        }
    }

    @ViewBuilder
    private func statusBadge(for status: ProgressOverallStatus) -> some View {
        let (text, color) = statusInfo(for: status)
        RFText(text, style: .captionBold, color: color)
            .padding(.horizontal, RFSpacing.xs)
            .padding(.vertical, RFSpacing.xxs)
            .background(color.opacity(0.15))
            .clipShape(Capsule())
    }

    private func statusInfo(for status: ProgressOverallStatus) -> (String, Color) {
        switch status {
        case .running:
            return (String(localized: "progress.status.running"), RFColors.fallbackPrimary)
        case .completed:
            return (String(localized: "progress.status.completed"), RFColors.success)
        case .failed:
            return (String(localized: "progress.status.failed"), RFColors.error)
        case .cancelled:
            return (String(localized: "progress.status.cancelled"), RFColors.warning)
        }
    }

    private func errorBanner(message: String) -> some View {
        HStack(spacing: RFSpacing.xs) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(RFColors.error)
                .font(.system(size: 14))

            RFText(message, style: .caption, color: RFColors.error)

            Spacer()

            Button {
                viewModel.dismissError()
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 12))
                    .foregroundStyle(RFColors.fallbackTextSecondary)
            }
        }
        .padding(RFSpacing.xs)
        .background(RFColors.error.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func completedBanner() -> some View {
        HStack(spacing: RFSpacing.xs) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(RFColors.success)
                .font(.system(size: 16))

            RFText(
                String(localized: "progress.completed.message"),
                style: .caption,
                color: RFColors.success
            )

            Spacer()
        }
        .padding(RFSpacing.xs)
        .background(RFColors.success.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .transition(.opacity)
    }
}

#Preview("Determinate - Running") {
    let viewModel = ProgressViewModel(
        observeProgressUseCase: ObserveProgressUseCase(
            repository: ProgressRepositoryImpl()
        )
    )

    ProgressContainerView(viewModel: viewModel)
        .onAppear {
            viewModel.updateProgress(
                ProgressState(
                    mode: .determinate,
                    percentage: 45,
                    taskDescription: "Proje derleniyor",
                    steps: [
                        ProgressStep(
                            type: .thinking,
                            label: "Analiz ediliyor",
                            status: .completed,
                            durationSeconds: 1.5
                        ),
                        ProgressStep(
                            type: .toolCalling,
                            label: "Docker build",
                            status: .active,
                            detail: "docker: build --tag app"
                        ),
                        ProgressStep(
                            type: .generating,
                            label: "Sonuc hazirlaniyor",
                            status: .pending
                        ),
                    ],
                    currentStepIndex: 1,
                    status: .running
                )
            )
        }
}

#Preview("Indeterminate") {
    let viewModel = ProgressViewModel(
        observeProgressUseCase: ObserveProgressUseCase(
            repository: ProgressRepositoryImpl()
        )
    )

    ProgressContainerView(viewModel: viewModel)
        .onAppear {
            viewModel.updateProgress(
                ProgressState(
                    mode: .indeterminate,
                    taskDescription: "AI dusunuyor...",
                    status: .running
                )
            )
        }
}
