import SwiftUI

/// RafRaf asamali ilerleme gostergesi.
/// Step-by-step ilerleme durumunu gorsel olarak gosterir.
/// Her adim icin durum (pending, active, completed, failed) animasyonlu gosterilir.
struct RFStepProgressView: View {
    /// Ilerleme adimlari.
    let steps: [ProgressStep]
    /// Mevcut aktif adim indexi.
    let currentStepIndex: Int?

    @State private var animationPhase: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
            ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                stepRow(step: step, index: index, isLast: index == steps.count - 1)
            }
        }
    }

    // MARK: - Private Views

    private func stepRow(step: ProgressStep, index: Int, isLast: Bool) -> some View {
        HStack(alignment: .top, spacing: RFSpacing.sm) {
            // Step indicator (sol kolon)
            VStack(spacing: 0) {
                stepIcon(for: step)
                    .frame(width: 24, height: 24)

                if !isLast {
                    stepConnector(isCompleted: step.status == .completed)
                }
            }

            // Step content (sag kolon)
            VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                HStack {
                    RFText(step.label, style: stepLabelStyle(for: step))

                    Spacer()

                    if let duration = step.durationSeconds {
                        RFText(
                            formatDuration(duration),
                            style: .caption,
                            color: RFColors.fallbackTextTertiary
                        )
                    }
                }

                if let detail = step.detail {
                    RFText(detail, style: .caption, color: RFColors.fallbackTextSecondary)
                        .lineLimit(2)
                }

                if step.status == .active {
                    stepTypeIndicator(type: step.type)
                        .padding(.top, RFSpacing.xxs)
                }
            }
            .padding(.bottom, isLast ? 0 : RFSpacing.xs)
        }
    }

    @ViewBuilder
    private func stepIcon(for step: ProgressStep) -> some View {
        switch step.status {
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(RFColors.success)
                .font(.system(size: 20))
                .transition(.scale.combined(with: .opacity))

        case .active:
            ZStack {
                Circle()
                    .fill(RFColors.fallbackPrimary.opacity(0.2))
                    .frame(width: 24, height: 24)
                    .scaleEffect(animationPhase ? 1.3 : 1.0)
                    .animation(
                        .easeInOut(duration: 1.0).repeatForever(autoreverses: true),
                        value: animationPhase
                    )

                Circle()
                    .fill(RFColors.fallbackPrimary)
                    .frame(width: 12, height: 12)
            }
            .onAppear { animationPhase = true }

        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundStyle(RFColors.error)
                .font(.system(size: 20))

        case .pending:
            Circle()
                .strokeBorder(RFColors.fallbackTextTertiary, lineWidth: 1.5)
                .frame(width: 20, height: 20)
        }
    }

    private func stepConnector(isCompleted: Bool) -> some View {
        Rectangle()
            .fill(isCompleted ? RFColors.success : RFColors.fallbackTextTertiary.opacity(0.3))
            .frame(width: 2, height: 24)
            .animation(.easeInOut(duration: 0.3), value: isCompleted)
    }

    @ViewBuilder
    private func stepTypeIndicator(type: ProgressStepType) -> some View {
        HStack(spacing: RFSpacing.xxs) {
            Image(systemName: iconName(for: type))
                .font(.system(size: 12))
                .foregroundStyle(RFColors.fallbackPrimary)

            RFText(
                localizedLabel(for: type),
                style: .caption,
                color: RFColors.fallbackPrimary
            )
        }
        .padding(.horizontal, RFSpacing.xs)
        .padding(.vertical, RFSpacing.xxs)
        .background(RFColors.fallbackPrimary.opacity(0.1))
        .clipShape(Capsule())
    }

    // MARK: - Helpers

    private func stepLabelStyle(for step: ProgressStep) -> RFTextStyle {
        switch step.status {
        case .active:
            return .bodyBold
        case .completed:
            return .body
        case .failed:
            return .body
        case .pending:
            return .caption
        }
    }

    private func iconName(for type: ProgressStepType) -> String {
        switch type {
        case .thinking:
            return "brain"
        case .toolCalling:
            return "wrench.and.screwdriver"
        case .generating:
            return "text.cursor"
        case .waitingApproval:
            return "hand.raised"
        }
    }

    private func localizedLabel(for type: ProgressStepType) -> String {
        switch type {
        case .thinking:
            return String(localized: "progress.type.thinking")
        case .toolCalling:
            return String(localized: "progress.type.toolCalling")
        case .generating:
            return String(localized: "progress.type.generating")
        case .waitingApproval:
            return String(localized: "progress.type.waitingApproval")
        }
    }

    private func formatDuration(_ seconds: Double) -> String {
        if seconds < 1 {
            return String(localized: "progress.duration.lessThanSecond")
        } else if seconds < 60 {
            return String(localized: "progress.duration.seconds.\(Int(seconds))")
        } else {
            let minutes = Int(seconds) / 60
            let remainingSeconds = Int(seconds) % 60
            return String(localized: "progress.duration.minutes.\(minutes).\(remainingSeconds)")
        }
    }
}

#Preview {
    let steps: [ProgressStep] = [
        ProgressStep(
            type: .thinking,
            label: String(localized: "progress.preview.step1"),
            status: .completed,
            durationSeconds: 2.3
        ),
        ProgressStep(
            type: .toolCalling,
            label: String(localized: "progress.preview.step2"),
            status: .active,
            detail: "docker: build"
        ),
        ProgressStep(
            type: .generating,
            label: String(localized: "progress.preview.step3"),
            status: .pending
        ),
        ProgressStep(
            type: .waitingApproval,
            label: String(localized: "progress.preview.step4"),
            status: .pending
        ),
    ]

    return RFStepProgressView(
        steps: steps,
        currentStepIndex: 1
    )
    .padding()
}
