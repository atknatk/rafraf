import SwiftUI

/// Tek bir task'in detaylarini gosteren ekran.
struct TaskDetailView: View {
    let task: AITask

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: RFSpacing.md) {
                // Baslik ve durum
                RFCard {
                    VStack(alignment: .leading, spacing: RFSpacing.sm) {
                        HStack {
                            Text(task.title)
                                .font(RFTypography.headline)
                            Spacer()
                            Text(task.status.displayName)
                                .font(RFTypography.caption)
                                .padding(.horizontal, RFSpacing.xs)
                                .padding(.vertical, RFSpacing.xxs)
                                .background(
                                    RoundedRectangle(cornerRadius: RFSpacing.xxs)
                                        .fill(task.status.isRunning ? Color.accentColor.opacity(0.1) : Color.secondary.opacity(0.1))
                                )
                        }

                        if let projectName = task.projectName {
                            Label(projectName, systemImage: "folder")
                                .font(RFTypography.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                // Ilerleme
                RFCard {
                    VStack(alignment: .leading, spacing: RFSpacing.sm) {
                        Text(String(localized: "task.detail.progress"))
                            .font(RFTypography.bodyBold)

                        ProgressView(value: task.progressFraction)
                            .tint(.accentColor)

                        HStack {
                            Text("\(task.progressPct)%")
                                .font(RFTypography.caption)
                            Spacer()
                            Text(String(localized: "task.detail.steps \(task.completedSteps) \(task.totalSteps)"))
                                .font(RFTypography.caption)
                                .foregroundStyle(.secondary)
                        }

                        if let currentStep = task.currentStep {
                            Label(currentStep, systemImage: "arrow.right.circle")
                                .font(RFTypography.body)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                // Prompt
                RFCard {
                    VStack(alignment: .leading, spacing: RFSpacing.xs) {
                        Text(String(localized: "task.detail.prompt"))
                            .font(RFTypography.bodyBold)
                        Text(task.prompt)
                            .font(RFTypography.body)
                            .foregroundStyle(.secondary)
                    }
                }

                // Sonuc veya hata
                if let resultSummary = task.resultSummary {
                    RFCard {
                        VStack(alignment: .leading, spacing: RFSpacing.xs) {
                            Text(String(localized: "task.detail.result"))
                                .font(RFTypography.bodyBold)
                            Text(resultSummary)
                                .font(RFTypography.body)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                if let errorMessage = task.errorMessage {
                    RFCard {
                        VStack(alignment: .leading, spacing: RFSpacing.xs) {
                            Label(
                                String(localized: "task.detail.error"),
                                systemImage: "exclamationmark.triangle"
                            )
                            .font(RFTypography.bodyBold)
                            .foregroundStyle(.red)
                            Text(errorMessage)
                                .font(RFTypography.body)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .padding(RFSpacing.md)
        }
        .navigationTitle(task.title)
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    NavigationStack {
        TaskDetailView(
            task: AITask(
                id: UUID(),
                title: "Implement login feature",
                prompt: "Add login screen with email/password authentication",
                taskType: "feature",
                status: .implementing,
                currentStep: "developer",
                totalSteps: 4,
                completedSteps: 2,
                progressPct: 50,
                resultSummary: nil,
                errorMessage: nil,
                projectName: "RafRaf",
                createdAt: Date(),
                startedAt: Date(),
                completedAt: nil
            )
        )
    }
}
