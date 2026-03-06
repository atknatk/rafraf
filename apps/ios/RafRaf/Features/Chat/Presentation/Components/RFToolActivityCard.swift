import SwiftUI

/// Claude Code tarzı inline tool aktivite karti.
/// AI islemi sirasinda hangi aracların calistigini gercek zamanli gosterir.
struct RFToolActivityCard: View {
    let activity: ToolActivityModel

    @State private var pulse = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            headerRow
            if !activity.steps.isEmpty {
                Divider()
                    .padding(.horizontal, RFSpacing.sm)
                stepsView
            }
        }
        .background(RFColors.fallbackSurface)
        .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))
        .overlay(
            RoundedRectangle(cornerRadius: RFCornerRadius.medium)
                .stroke(
                    activity.isCompleted
                        ? RFColors.success.opacity(0.3)
                        : RFColors.fallbackPrimary.opacity(0.2),
                    lineWidth: 1
                )
        )
        .padding(.horizontal, RFSpacing.md)
        .onAppear {
            withAnimation(
                .easeInOut(duration: 1.0).repeatForever(autoreverses: true)
            ) {
                pulse = true
            }
        }
    }

    // MARK: - Header

    private var headerRow: some View {
        HStack(spacing: RFSpacing.xs) {
            // Status icon
            if activity.isCompleted {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(RFColors.success)
            } else {
                ZStack {
                    Circle()
                        .fill(RFColors.fallbackPrimary.opacity(pulse ? 0.15 : 0.05))
                        .frame(width: 20, height: 20)
                    ProgressView()
                        .controlSize(.mini)
                        .tint(RFColors.fallbackPrimary)
                }
            }

            RFText(
                activity.phaseLabel,
                style: .captionBold,
                color: activity.isCompleted ? RFColors.success : RFColors.fallbackTextPrimary
            )
            .lineLimit(1)

            Spacer()

            // Percentage badge
            if !activity.isCompleted && activity.percentage > 0 {
                Text("\(activity.percentage)%")
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundStyle(RFColors.fallbackPrimary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 2)
                    .background(RFColors.fallbackPrimary.opacity(0.1))
                    .clipShape(Capsule())
            }
        }
        .padding(.horizontal, RFSpacing.sm)
        .padding(.vertical, RFSpacing.xs + 2)
    }

    // MARK: - Steps

    private var stepsView: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Show last 5 steps; always show active/latest
            let visibleSteps = Array(activity.steps.suffix(5))
            ForEach(visibleSteps) { step in
                stepRow(step)
            }
        }
        .padding(.vertical, RFSpacing.xxs)
    }

    private func stepRow(_ step: ToolStep) -> some View {
        HStack(alignment: .top, spacing: RFSpacing.xs) {
            // Step status icon
            Group {
                if step.status == "active" {
                    Circle()
                        .fill(RFColors.fallbackPrimary.opacity(pulse ? 0.8 : 0.4))
                        .frame(width: 6, height: 6)
                        .padding(.top, 5)
                } else if step.status == "completed" {
                    Image(systemName: "checkmark")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundStyle(RFColors.success)
                        .frame(width: 6, height: 6)
                        .padding(.top, 4)
                } else if step.status == "failed" {
                    Image(systemName: "xmark")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundStyle(RFColors.error)
                        .frame(width: 6, height: 6)
                        .padding(.top, 4)
                } else {
                    Circle()
                        .fill(RFColors.fallbackTextTertiary.opacity(0.3))
                        .frame(width: 6, height: 6)
                        .padding(.top, 5)
                }
            }
            .frame(width: 14, alignment: .center)

            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: RFSpacing.xs) {
                    Text(step.label)
                        .font(.system(size: 12, weight: step.status == "active" ? .semibold : .regular))
                        .foregroundStyle(
                            step.status == "active"
                                ? RFColors.fallbackTextPrimary
                                : RFColors.fallbackTextSecondary
                        )
                        .lineLimit(1)

                    Spacer()

                    if let duration = step.durationSeconds, step.status == "completed" {
                        Text(String(format: "%.1fs", duration))
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(RFColors.fallbackTextTertiary)
                    }
                }

                if let detail = step.detail, !detail.isEmpty {
                    Text(detail)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(
                            step.status == "active"
                                ? RFColors.fallbackPrimary.opacity(0.8)
                                : RFColors.fallbackTextTertiary
                        )
                        .lineLimit(1)
                }
            }
        }
        .padding(.horizontal, RFSpacing.sm)
        .padding(.vertical, 3)
    }
}

#Preview {
    ScrollView {
        VStack(spacing: RFSpacing.md) {
            // Active state
            RFToolActivityCard(
                activity: ToolActivityModel(
                    phase: "tool_calling",
                    phaseLabel: "Dosya okunuyor...",
                    percentage: 42,
                    steps: [
                        ToolStep(id: "1", label: "Düşünüyor...", status: "completed", detail: nil, durationSeconds: 0.2),
                        ToolStep(id: "2", label: "Dosya okunuyor", status: "completed", detail: "apps/ios/ChatView.swift", durationSeconds: 0.3),
                        ToolStep(id: "3", label: "Komut çalıştırılıyor", status: "active", detail: "xcodebuild build -scheme...", durationSeconds: nil),
                    ]
                )
            )

            // Completed state
            RFToolActivityCard(
                activity: ToolActivityModel(
                    phase: "completed",
                    phaseLabel: "Tamamlandı",
                    percentage: 100,
                    steps: [
                        ToolStep(id: "1", label: "Düşünüyor...", status: "completed", detail: nil, durationSeconds: 0.2),
                        ToolStep(id: "2", label: "Dosya okunuyor", status: "completed", detail: "apps/ios/ChatView.swift", durationSeconds: 0.4),
                        ToolStep(id: "3", label: "İçerik aranıyor", status: "completed", detail: "\"progressViewModel\"", durationSeconds: 0.1),
                    ]
                )
            )
        }
        .padding(.vertical, RFSpacing.md)
    }
    .background(RFColors.fallbackBackground)
}
