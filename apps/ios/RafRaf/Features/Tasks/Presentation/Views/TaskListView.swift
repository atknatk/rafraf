import SwiftUI

/// Aktif task'larin listesini gosteren ekran.
struct TaskListView: View {
    @State private var viewModel: TaskListViewModel

    init(viewModel: TaskListViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        contentView
            .navigationTitle(String(localized: "task.list.title"))
            .task {
                await viewModel.loadActiveTasks()
            }
            .alert(
                String(localized: "task.error.title"),
                isPresented: .init(
                    get: { viewModel.errorMessage != nil },
                    set: { if !$0 { viewModel.dismissError() } }
                )
            ) {
                Button(String(localized: "task.error.dismiss"), role: .cancel) {
                    viewModel.dismissError()
                }
            } message: {
                if let errorMessage = viewModel.errorMessage {
                    Text(errorMessage)
                }
            }
    }

    @ViewBuilder
    private var contentView: some View {
        if viewModel.isLoading {
            ProgressView()
        } else if viewModel.showsEmptyState {
            RFEmptyStateView(
                systemImage: "checklist",
                title: String(localized: "task.empty.title"),
                message: String(localized: "task.empty.message")
            )
        } else {
            List(viewModel.tasks) { task in
                NavigationLink(value: task.id) {
                    TaskRowView(task: task)
                }
                .swipeActions(edge: .trailing) {
                    if task.status.isRunning {
                        Button(role: .destructive) {
                            Task {
                                await viewModel.cancelTask(taskId: task.id)
                            }
                        } label: {
                            Label(
                                String(localized: "task.action.cancel"),
                                systemImage: "xmark.circle"
                            )
                        }
                    }
                }
            }
        }
    }
}

/// Tek bir task satirini gosteren view.
private struct TaskRowView: View {
    let task: AITask

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xs) {
            HStack {
                Text(task.title)
                    .font(RFTypography.bodyBold)
                Spacer()
                Text(task.status.displayName)
                    .font(RFTypography.caption)
                    .foregroundStyle(task.status.isRunning ? Color.accentColor : .secondary)
            }

            if let currentStep = task.currentStep {
                Text(currentStep)
                    .font(RFTypography.caption)
                    .foregroundStyle(.secondary)
            }

            ProgressView(value: task.progressFraction)
                .tint(task.status.isRunning ? .accentColor : .secondary)
        }
        .padding(.vertical, RFSpacing.xxs)
    }
}

#Preview {
    NavigationStack {
        TaskListView(
            viewModel: TaskListViewModel(
                repository: PreviewTaskRepository()
            )
        )
    }
}

/// Preview icin mock repository.
private final class PreviewTaskRepository: TaskRepository, @unchecked Sendable {
    func getActiveTasks() async throws -> [AITask] {
        [
            AITask(
                id: UUID(),
                title: "Implement login feature",
                prompt: "Add login",
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
        ]
    }

    func getTaskDetail(taskId: UUID) async throws -> AITask {
        AITask(
            id: taskId,
            title: "Task detail",
            prompt: "Detail",
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
    }

    func createTask(title: String, prompt: String, taskType: String, projectId: UUID?) async throws -> AITask {
        AITask(
            id: UUID(),
            title: title,
            prompt: prompt,
            taskType: taskType,
            status: .queued,
            currentStep: nil,
            totalSteps: 4,
            completedSteps: 0,
            progressPct: 0,
            resultSummary: nil,
            errorMessage: nil,
            projectName: nil,
            createdAt: Date(),
            startedAt: nil,
            completedAt: nil
        )
    }

    func cancelTask(taskId: UUID) async throws {}
    func registerLiveActivityToken(taskId: UUID, pushToken: String) async throws {}
}
