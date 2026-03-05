import SwiftUI

/// Agent listesi ekrani.
/// Bagli host agent'lari filtreleyip goruntuleyebildigi ekran.
/// Pull-to-refresh, skeleton ve durum filtresi destegi.
struct AgentListView: View {
    @State private var viewModel: AgentListViewModel
    @Namespace private var filterNamespace

    init(viewModel: AgentListViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                filterBar
                contentView
            }
            .navigationTitle(String(localized: "agent.list.title"))
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    liveIndicator
                }
            }
            .task {
                await viewModel.loadAgents()
                viewModel.startAutoRefresh()
            }
            .onDisappear {
                viewModel.stopAutoRefresh()
            }
            .refreshable {
                await viewModel.refreshAgents()
            }
            .overlay {
                if let errorMessage = viewModel.errorMessage {
                    errorBanner(message: errorMessage)
                }
            }
        }
    }

    // MARK: - Live Indicator

    private var liveIndicator: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(viewModel.onlineCount > 0 ? RFColors.success : RFColors.fallbackTextTertiary)
                .frame(width: 6, height: 6)
            if let refreshedAt = viewModel.lastRefreshedAt {
                RFText(
                    relativeTime(refreshedAt),
                    style: .caption,
                    color: RFColors.fallbackTextTertiary
                )
            }
        }
    }

    private func relativeTime(_ date: Date) -> String {
        let seconds = Int(-date.timeIntervalSinceNow)
        if seconds < 5 { return String(localized: "agent.refresh.justNow") }
        if seconds < 60 { return "\(seconds)s" }
        return "\(seconds / 60)m"
    }

    // MARK: - Filter Bar

    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: RFSpacing.xs) {
                filterChip(
                    title: String(localized: "agent.filter.all"),
                    isSelected: viewModel.selectedFilter == nil
                ) {
                    Task { await viewModel.filterByStatus(nil) }
                }

                ForEach(AgentStatus.allCases, id: \.self) { status in
                    filterChip(
                        title: filterTitle(for: status),
                        isSelected: viewModel.selectedFilter == status
                    ) {
                        Task { await viewModel.filterByStatus(status) }
                    }
                }
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
        }
        .background(RFColors.fallbackBackground)
    }

    private func filterChip(
        title: String,
        isSelected: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button {
            action()
        } label: {
            RFText(
                title,
                style: .captionBold,
                color: isSelected ? .white : RFColors.fallbackTextPrimary
            )
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.xs)
            .background {
                if isSelected {
                    RFColors.brandGradient
                        .matchedGeometryEffect(
                            id: "activeFilter",
                            in: filterNamespace
                        )
                } else {
                    RFColors.fallbackSurface
                }
            }
            .clipShape(Capsule())
        }
        .buttonStyle(RFPressButtonStyle())
        .sensoryFeedback(.selection, trigger: isSelected)
    }

    private func filterTitle(for status: AgentStatus) -> String {
        switch status {
        case .online:
            return String(localized: "agent.filter.online")
        case .offline:
            return String(localized: "agent.filter.offline")
        case .busy:
            return String(localized: "agent.filter.busy")
        }
    }

    // MARK: - Content

    @ViewBuilder
    private var contentView: some View {
        if viewModel.isLoading {
            AgentListSkeletonView()
        } else if viewModel.agents.isEmpty {
            agentEmptyStateView
        } else {
            agentList
        }
    }

    private var agentEmptyStateView: some View {
        ScrollView {
            VStack(spacing: RFSpacing.xl) {
                Spacer()
                    .frame(height: RFSpacing.xl)

                VStack(spacing: RFSpacing.md) {
                    Image(systemName: "desktopcomputer")
                        .font(.system(size: 64, weight: .thin))
                        .foregroundStyle(RFColors.fallbackTextTertiary)

                    VStack(spacing: RFSpacing.xs) {
                        RFText(
                            String(localized: "agent.empty.title"),
                            style: .title,
                            color: RFColors.fallbackTextPrimary
                        )
                        .multilineTextAlignment(.center)

                        RFText(
                            String(localized: "agent.empty.message"),
                            style: .body,
                            color: RFColors.fallbackTextSecondary
                        )
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, RFSpacing.lg)
                    }
                }

                VStack(spacing: RFSpacing.sm) {
                    RFCard {
                        VStack(alignment: .leading, spacing: RFSpacing.sm) {
                            settingsStep(
                                number: "1",
                                title: String(localized: "agent.setup.step1.title"),
                                detail: String(localized: "agent.setup.step1.detail")
                            )
                            Divider()
                            settingsStep(
                                number: "2",
                                title: String(localized: "agent.setup.step2.title"),
                                detail: String(localized: "agent.setup.step2.detail")
                            )
                            Divider()
                            settingsStep(
                                number: "3",
                                title: String(localized: "agent.setup.step3.title"),
                                detail: String(localized: "agent.setup.step3.detail")
                            )
                        }
                    }
                }
                .padding(.horizontal, RFSpacing.md)
            }
            .frame(maxWidth: .infinity)
            .padding(.bottom, RFSpacing.xxxl)
        }
        .refreshable {
            await viewModel.refreshAgents()
        }
    }

    private func settingsStep(number: String, title: String, detail: String) -> some View {
        HStack(alignment: .top, spacing: RFSpacing.sm) {
            Text(number)
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
                .frame(width: 24, height: 24)
                .background(RFColors.fallbackPrimary)
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 2) {
                RFText(title, style: .bodyBold, color: RFColors.fallbackTextPrimary)
                RFText(detail, style: .caption, color: RFColors.fallbackTextSecondary)
            }
        }
    }

    private var agentList: some View {
        ScrollView {
            LazyVStack(spacing: RFSpacing.sm) {
                ForEach(viewModel.agents) { agent in
                    NavigationLink {
                        AgentDetailView(
                            agent: agent,
                            getUsageUseCase: viewModel.getSubscriptionUsageUseCase,
                            refreshUsageUseCase: viewModel.refreshSubscriptionUsageUseCase,
                            getAgentProjectsUseCase: viewModel.getAgentProjectsUseCase,
                            setProjectActiveUseCase: viewModel.setProjectActiveUseCase,
                            getClaudeProcessesUseCase: viewModel.getClaudeProcessesUseCase,
                            getAgentTasksUseCase: viewModel.getAgentTasksUseCase,
                            cancelAgentTaskUseCase: viewModel.cancelAgentTaskUseCase
                        )
                    } label: {
                        AgentCardView(agent: agent)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
        }
    }

    // MARK: - Error Banner

    private func errorBanner(message: String) -> some View {
        VStack {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(RFColors.error)
                RFText(message, style: .body, color: .white)
                Spacer()
                RFButton(
                    String(localized: "agent.error.dismiss"),
                    style: .ghost,
                    size: .small
                ) {
                    viewModel.dismissError()
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
    let repo = PreviewAgentRepository()
    AgentListView(
        viewModel: AgentListViewModel(
            getAgentsUseCase: GetAgentsUseCase(repository: repo),
            getSubscriptionUsageUseCase: GetSubscriptionUsageUseCase(repository: repo),
            refreshSubscriptionUsageUseCase: RefreshSubscriptionUsageUseCase(repository: repo),
            getAgentProjectsUseCase: GetAgentProjectsUseCase(repository: repo),
            setProjectActiveUseCase: SetProjectActiveUseCase(repository: repo),
            getClaudeProcessesUseCase: GetClaudeProcessesUseCase(repository: repo),
            getAgentTasksUseCase: GetAgentTasksUseCase(repository: repo),
            cancelAgentTaskUseCase: CancelAgentTaskUseCase(repository: repo)
        )
    )
}

/// Preview icin mock repository.
final class PreviewAgentRepository: AgentRepositoryProtocol, @unchecked Sendable {
    func getSubscriptionUsage() async throws -> SubscriptionUsage {
        SubscriptionUsage(
            subscriptionType: "max",
            email: "test@example.com",
            orgName: "Test Org",
            todayUsage: DailyUsageStats(date: "2026-03-04", messageCount: 142, sessionCount: 5, toolCallCount: 87),
            recentDays: [
                DailyUsageStats(date: "2026-02-26", messageCount: 98, sessionCount: 3, toolCallCount: 45),
                DailyUsageStats(date: "2026-02-27", messageCount: 210, sessionCount: 8, toolCallCount: 120),
                DailyUsageStats(date: "2026-02-28", messageCount: 156, sessionCount: 4, toolCallCount: 78),
                DailyUsageStats(date: "2026-03-01", messageCount: 45, sessionCount: 2, toolCallCount: 22),
                DailyUsageStats(date: "2026-03-02", messageCount: 189, sessionCount: 6, toolCallCount: 95),
                DailyUsageStats(date: "2026-03-03", messageCount: 301, sessionCount: 9, toolCallCount: 150),
                DailyUsageStats(date: "2026-03-04", messageCount: 142, sessionCount: 5, toolCallCount: 87)
            ],
            totalMessagesToday: 12,
            isRateLimited: false,
            rateLimitResetAt: nil,
            lastFetchedAt: Date().addingTimeInterval(-180)
        )
    }

    func refreshSubscriptionUsage() async throws -> SubscriptionUsage {
        try await getSubscriptionUsage()
    }

    func getAgents(status: AgentStatus?) async throws -> AgentListResult {
        let allAgents = [
            Agent(
                hostId: "macbook-pro",
                status: .online,
                capabilities: [.shell, .docker, .git, .python, .maestroIos, .xcodeBuild],
                osInfo: "Darwin 24.1.0",
                uptimeSeconds: 7200,
                activeTasks: 2,
                lastHeartbeatAt: Date(),
                resources: AgentResourceInfo(
                    cpuUsagePercent: 45,
                    memoryUsagePercent: 72,
                    diskUsagePercent: 38,
                    diskFreeGb: 120
                )
            ),
            Agent(
                hostId: "ubuntu-server",
                status: .online,
                capabilities: [.shell, .docker, .playwright, .git, .python, .nodejs],
                osInfo: "Linux 6.1.0",
                uptimeSeconds: 86400,
                activeTasks: 0,
                lastHeartbeatAt: Date(),
                resources: AgentResourceInfo(
                    cpuUsagePercent: 12,
                    memoryUsagePercent: 45,
                    diskUsagePercent: 65,
                    diskFreeGb: 80
                )
            ),
            Agent(
                hostId: "imac-dev",
                status: .offline,
                capabilities: [.shell, .git],
                osInfo: "Darwin 23.5.0",
                uptimeSeconds: nil,
                activeTasks: nil,
                lastHeartbeatAt: Date().addingTimeInterval(-3600),
                resources: nil
            )
        ]

        let filtered: [Agent]
        if let status {
            filtered = allAgents.filter { $0.status == status }
        } else {
            filtered = allAgents
        }

        let onlineCount = allAgents.filter { $0.status == .online || $0.status == .busy }.count

        return AgentListResult(
            agents: filtered,
            total: filtered.count,
            onlineCount: onlineCount
        )
    }

    func getAgentProjects(agentId: String) async throws -> [AgentProject] {
        [
            AgentProject(
                agentId: agentId,
                projectId: "proj-1",
                projectName: "RafRaf",
                isActive: true,
                repositoryUrl: "https://github.com/atknatk/rafraf",
                localPath: "/Users/atakan/Projects/rafraf",
                techStack: ["Swift", "Python"]
            ),
            AgentProject(
                agentId: agentId,
                projectId: "proj-2",
                projectName: "SideProject",
                isActive: false,
                repositoryUrl: nil,
                localPath: nil,
                techStack: ["TypeScript"]
            )
        ]
    }

    func setProjectActive(agentId: String, projectId: String, isActive: Bool) async throws -> AgentProject {
        AgentProject(
            agentId: agentId,
            projectId: projectId,
            projectName: "RafRaf",
            isActive: isActive,
            repositoryUrl: nil,
            localPath: nil,
            techStack: []
        )
    }

    func getClaudeProcesses(agentId: String) async throws -> [ClaudeProcess] {
        [
            ClaudeProcess(
                pid: 12345,
                cpuPercent: 23.5,
                memoryMb: 512.0,
                startedAt: Date().addingTimeInterval(-1800),
                cmdline: "claude --dangerously-skip-permissions"
            ),
            ClaudeProcess(
                pid: 12390,
                cpuPercent: 8.2,
                memoryMb: 256.0,
                startedAt: Date().addingTimeInterval(-900),
                cmdline: "claude -p 'RafRaf görev'"
            )
        ]
    }

    func getAllAgentProjects() async throws -> [AgentProject] { [] }

    func getAgentTasks(agentId: String, limit: Int) async throws -> AgentTaskListResult {
        AgentTaskListResult(
            tasks: [
                AgentTask(
                    id: "task-1",
                    hostId: agentId,
                    runner: "shell",
                    action: "run",
                    status: .completed,
                    projectId: nil,
                    createdAt: Date().addingTimeInterval(-120),
                    startedAt: Date().addingTimeInterval(-119),
                    completedAt: Date().addingTimeInterval(-110),
                    durationMs: 9000,
                    error: nil
                ),
                AgentTask(
                    id: "task-2",
                    hostId: agentId,
                    runner: "docker",
                    action: "build",
                    status: .running,
                    projectId: "proj-1",
                    createdAt: Date().addingTimeInterval(-30),
                    startedAt: Date().addingTimeInterval(-29),
                    completedAt: nil,
                    durationMs: nil,
                    error: nil
                )
            ],
            total: 2,
            pendingCount: 1
        )
    }

    func cancelAgentTask(agentId: String, taskId: String) async throws {}
}
