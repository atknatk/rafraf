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
            .task {
                await viewModel.loadAgents()
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
            Spacer()
            RFEmptyStateView(
                systemImage: "desktopcomputer",
                title: String(localized: "agent.empty.title"),
                message: String(localized: "agent.empty.message")
            )
            Spacer()
        } else {
            agentList
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
                            getClaudeProcessesUseCase: viewModel.getClaudeProcessesUseCase
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
            getClaudeProcessesUseCase: GetClaudeProcessesUseCase(repository: repo)
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
}
