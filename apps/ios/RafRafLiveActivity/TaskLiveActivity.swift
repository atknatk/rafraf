import ActivityKit
import SwiftUI
import WidgetKit

/// Task Live Activity — Dynamic Island + Lock Screen UI.
/// AI task pipeline ilerlemesini gosterir.
struct TaskLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: TaskActivityAttributes.self) { context in
            // Lock Screen / Banner Live Activity view
            lockScreenView(context: context)
        } dynamicIsland: { context in
            DynamicIsland {
                // Expanded Dynamic Island
                DynamicIslandExpandedRegion(.leading) {
                    Image(systemName: context.state.phaseIcon)
                        .font(.title2)
                        .foregroundStyle(statusColor(for: context.state.status))
                }

                DynamicIslandExpandedRegion(.trailing) {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("\(Int(context.state.progress * 100))%")
                            .font(.headline)
                            .monospacedDigit()

                        if let eta = context.state.estimatedSecondsRemaining, eta > 0 {
                            Text(formattedETA(seconds: eta))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                DynamicIslandExpandedRegion(.center) {
                    Text(context.attributes.taskTitle)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .lineLimit(1)
                }

                DynamicIslandExpandedRegion(.bottom) {
                    VStack(spacing: 6) {
                        ProgressView(value: context.state.progress)
                            .tint(statusColor(for: context.state.status))

                        HStack {
                            Text(context.state.currentStep)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)

                            Spacer()

                            Text("\(context.state.completedSteps)/\(context.state.totalSteps)")
                                .font(.caption)
                                .monospacedDigit()
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.horizontal, 4)
                }
            } compactLeading: {
                // Compact leading: faz ikonu
                Image(systemName: context.state.phaseIcon)
                    .foregroundStyle(statusColor(for: context.state.status))
            } compactTrailing: {
                // Compact trailing: progress yuzde
                Text("\(Int(context.state.progress * 100))%")
                    .font(.caption)
                    .monospacedDigit()
            } minimal: {
                // Minimal: sadece faz ikonu
                Image(systemName: context.state.phaseIcon)
                    .foregroundStyle(statusColor(for: context.state.status))
            }
        }
    }

    // MARK: - Lock Screen View

    @ViewBuilder
    private func lockScreenView(context: ActivityViewContext<TaskActivityAttributes>) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: context.state.phaseIcon)
                    .font(.title3)
                    .foregroundStyle(statusColor(for: context.state.status))

                VStack(alignment: .leading, spacing: 2) {
                    Text(context.attributes.projectName)
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Text(context.attributes.taskTitle)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .lineLimit(1)
                }

                Spacer()

                Text("\(Int(context.state.progress * 100))%")
                    .font(.title3)
                    .fontWeight(.bold)
                    .monospacedDigit()
            }

            ProgressView(value: context.state.progress)
                .tint(statusColor(for: context.state.status))

            HStack {
                Text(context.state.currentStep)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                Spacer()

                if let eta = context.state.estimatedSecondsRemaining, eta > 0 {
                    Text(formattedETA(seconds: eta))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Text("\(context.state.completedSteps)/\(context.state.totalSteps)")
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
    }

    // MARK: - Helpers

    /// Status'a gore renk secimi.
    private func statusColor(for status: String) -> Color {
        switch status {
        case "implementing", "planning", "started":
            return .blue
        case "testing":
            return .orange
        case "reviewing":
            return .purple
        case "completed":
            return .green
        case "failed":
            return .red
        case "cancelled":
            return .gray
        default:
            return .blue
        }
    }

    /// Kalan sureyi formatla.
    private func formattedETA(seconds: Int) -> String {
        if seconds < 60 {
            return "\(seconds)s"
        } else {
            let minutes = seconds / 60
            let remainingSeconds = seconds % 60
            if remainingSeconds == 0 {
                return "\(minutes)m"
            }
            return "\(minutes)m \(remainingSeconds)s"
        }
    }
}
