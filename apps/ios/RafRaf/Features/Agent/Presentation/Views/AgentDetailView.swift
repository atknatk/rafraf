import Factory
import SwiftUI

/// Agent detay ekrani.
/// Agent bilgileri ve Claude Max subscription kullanim durumunu gosterir.
struct AgentDetailView: View {
    let agent: Agent
    @State private var subscriptionUsage: SubscriptionUsage?
    @State private var agentProjects: [AgentProject] = []
    @State private var claudeProcesses: [ClaudeProcess] = []
    @State private var isRefreshing = false
    @State private var errorMessage: String?

    private let getUsageUseCase: GetSubscriptionUsageUseCase
    private let refreshUsageUseCase: RefreshSubscriptionUsageUseCase
    private let getAgentProjectsUseCase: GetAgentProjectsUseCase
    private let setProjectActiveUseCase: SetProjectActiveUseCase
    private let getClaudeProcessesUseCase: GetClaudeProcessesUseCase

    init(
        agent: Agent,
        getUsageUseCase: GetSubscriptionUsageUseCase,
        refreshUsageUseCase: RefreshSubscriptionUsageUseCase,
        getAgentProjectsUseCase: GetAgentProjectsUseCase,
        setProjectActiveUseCase: SetProjectActiveUseCase,
        getClaudeProcessesUseCase: GetClaudeProcessesUseCase
    ) {
        self.agent = agent
        self.getUsageUseCase = getUsageUseCase
        self.refreshUsageUseCase = refreshUsageUseCase
        self.getAgentProjectsUseCase = getAgentProjectsUseCase
        self.setProjectActiveUseCase = setProjectActiveUseCase
        self.getClaudeProcessesUseCase = getClaudeProcessesUseCase
    }

    var body: some View {
        ScrollView {
            VStack(spacing: RFSpacing.md) {
                agentInfoSection
                if !agentProjects.isEmpty {
                    projectsSection
                }
                if !claudeProcesses.isEmpty {
                    claudeProcessesSection
                }
                subscriptionSection
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
        }
        .background(RFColors.fallbackBackground)
        .navigationTitle(agent.hostId)
        .navigationBarTitleDisplayMode(.large)
        .task {
            async let usageTask: () = loadUsage()
            async let projectsTask: () = loadProjects()
            async let processesTask: () = loadProcesses()
            _ = await (usageTask, projectsTask, processesTask)
        }
        .overlay {
            if let errorMessage {
                errorBanner(message: errorMessage)
            }
        }
    }

    // MARK: - Agent Info Section

    private var agentInfoSection: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                        RFText(agent.hostId, style: .headline)
                        if let osInfo = agent.osInfo {
                            RFText(osInfo, style: .caption, color: RFColors.fallbackTextSecondary)
                        }
                    }
                    Spacer()
                    AgentStatusBadge(status: agent.status)
                }

                // Capabilities
                FlowLayout(spacing: RFSpacing.xxs) {
                    ForEach(agent.capabilities, id: \.self) { capability in
                        RFText(
                            capabilityLabel(capability),
                            style: .captionBold,
                            color: RFColors.fallbackTextSecondary
                        )
                        .padding(.horizontal, RFSpacing.xs)
                        .padding(.vertical, RFSpacing.xxs)
                        .background(RFColors.fallbackSurface)
                        .clipShape(Capsule())
                    }
                }

                // Resources
                if let resources = agent.resources {
                    resourceBars(resources)
                }

                // Footer
                HStack {
                    if let activeTasks = agent.activeTasks {
                        HStack(spacing: RFSpacing.xxs) {
                            Image(systemName: "terminal")
                                .font(.caption2)
                                .foregroundStyle(RFColors.fallbackTextTertiary)
                            RFText(
                                "\(activeTasks) \(String(localized: "agent.activeTasks"))",
                                style: .caption,
                                color: RFColors.fallbackTextTertiary
                            )
                        }
                    }
                    Spacer()
                    if let uptime = agent.uptimeSeconds {
                        RFText(
                            formatUptime(uptime),
                            style: .caption,
                            color: RFColors.fallbackTextTertiary
                        )
                    }
                }
            }
        }
    }

    // MARK: - Subscription Section

    private var subscriptionSection: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                // Header with refresh button
                HStack {
                    RFText(
                        String(localized: "agent.subscription.title"),
                        style: .headline
                    )
                    Spacer()
                    RFButton(
                        String(localized: "agent.subscription.refresh"),
                        style: .ghost,
                        size: .small
                    ) {
                        Task { await refreshUsage() }
                    }
                    .disabled(isRefreshing)
                }

                if let usage = subscriptionUsage {
                    subscriptionContent(usage)
                } else if isRefreshing {
                    HStack {
                        Spacer()
                        ProgressView()
                        Spacer()
                    }
                    .padding(.vertical, RFSpacing.md)
                } else {
                    RFText(
                        String(localized: "agent.subscription.unavailable"),
                        style: .body,
                        color: RFColors.fallbackTextSecondary
                    )
                }
            }
        }
    }

    @ViewBuilder
    private func subscriptionContent(_ usage: SubscriptionUsage) -> some View {
        // Plan type badge
        HStack(spacing: RFSpacing.xs) {
            RFText(
                String(localized: "agent.subscription.type"),
                style: .caption,
                color: RFColors.fallbackTextSecondary
            )
            RFText(
                usage.subscriptionType.uppercased(),
                style: .captionBold,
                color: .white
            )
            .padding(.horizontal, RFSpacing.sm)
            .padding(.vertical, RFSpacing.xxs)
            .background(RFColors.brandGradient)
            .clipShape(Capsule())

            Spacer()

            // Rate limit status
            HStack(spacing: RFSpacing.xxs) {
                Circle()
                    .fill(usage.isRateLimited ? RFColors.error : RFColors.success)
                    .frame(width: 8, height: 8)
                RFText(
                    usage.isRateLimited
                        ? String(localized: "agent.subscription.rateLimited")
                        : String(localized: "agent.subscription.normal"),
                    style: .caption,
                    color: usage.isRateLimited ? RFColors.error : RFColors.success
                )
            }
        }

        Divider()

        // Today's usage stats
        HStack(spacing: RFSpacing.md) {
            usageStat(
                label: String(localized: "agent.subscription.todayMessages"),
                value: "\(usage.todayUsage.messageCount)",
                icon: "message"
            )
            usageStat(
                label: String(localized: "agent.subscription.todaySessions"),
                value: "\(usage.todayUsage.sessionCount)",
                icon: "rectangle.stack"
            )
            usageStat(
                label: String(localized: "agent.subscription.todayTools"),
                value: "\(usage.todayUsage.toolCallCount)",
                icon: "wrench"
            )
        }

        // claude -p message count
        if usage.totalMessagesToday > 0 {
            HStack(spacing: RFSpacing.xxs) {
                Image(systemName: "terminal")
                    .font(.caption2)
                    .foregroundStyle(RFColors.fallbackTextTertiary)
                RFText(
                    "claude -p: \(usage.totalMessagesToday) \(String(localized: "agent.subscription.todayMessages").lowercased())",
                    style: .caption,
                    color: RFColors.fallbackTextTertiary
                )
            }
        }

        // Weekly chart
        if !usage.recentDays.isEmpty {
            Divider()

            RFText(
                String(localized: "agent.subscription.weeklyChart"),
                style: .captionBold,
                color: RFColors.fallbackTextSecondary
            )

            weeklyChart(days: usage.recentDays)
        }

        Divider()

        // Last updated
        HStack {
            Image(systemName: "clock")
                .font(.caption2)
                .foregroundStyle(RFColors.fallbackTextTertiary)
            RFText(
                "\(String(localized: "agent.subscription.lastUpdated")): \(relativeTime(from: usage.lastFetchedAt))",
                style: .caption,
                color: RFColors.fallbackTextTertiary
            )
            Spacer()
        }
    }

    // MARK: - Weekly Chart

    private func weeklyChart(days: [DailyUsageStats]) -> some View {
        let maxCount = days.map(\.messageCount).max() ?? 1

        return HStack(alignment: .bottom, spacing: RFSpacing.xxs) {
            ForEach(days) { day in
                VStack(spacing: RFSpacing.xxs) {
                    RFText(
                        "\(day.messageCount)",
                        style: .caption,
                        color: RFColors.fallbackTextTertiary
                    )
                    .font(.system(size: 9))

                    RoundedRectangle(cornerRadius: 3)
                        .fill(RFColors.fallbackPrimary.opacity(0.7))
                        .frame(
                            height: max(
                                4,
                                CGFloat(day.messageCount) / CGFloat(max(maxCount, 1)) * 50
                            )
                        )

                    RFText(
                        shortDay(day.date),
                        style: .caption,
                        color: RFColors.fallbackTextTertiary
                    )
                    .font(.system(size: 9))
                }
                .frame(maxWidth: .infinity)
            }
        }
        .frame(height: 80)
    }

    // MARK: - Usage Stat

    private func usageStat(label: String, value: String, icon: String) -> some View {
        VStack(spacing: RFSpacing.xxs) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundStyle(RFColors.fallbackPrimary)
            RFText(value, style: .headline)
            RFText(label, style: .caption, color: RFColors.fallbackTextSecondary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Resources

    private func resourceBars(_ resources: AgentResourceInfo) -> some View {
        VStack(spacing: RFSpacing.xs) {
            resourceBar(
                label: String(localized: "agent.resource.cpu"),
                value: resources.cpuUsagePercent,
                color: barColor(for: resources.cpuUsagePercent)
            )
            resourceBar(
                label: String(localized: "agent.resource.memory"),
                value: resources.memoryUsagePercent,
                color: barColor(for: resources.memoryUsagePercent)
            )
            resourceBar(
                label: String(localized: "agent.resource.disk"),
                value: resources.diskUsagePercent,
                color: barColor(for: resources.diskUsagePercent)
            )
        }
    }

    private func resourceBar(label: String, value: Double, color: Color) -> some View {
        HStack(spacing: RFSpacing.xs) {
            RFText(label, style: .caption, color: RFColors.fallbackTextSecondary)
                .frame(width: 50, alignment: .leading)
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: RFCornerRadius.small)
                        .fill(RFColors.fallbackSurface)
                    RoundedRectangle(cornerRadius: RFCornerRadius.small)
                        .fill(color)
                        .frame(width: geometry.size.width * min(value / 100.0, 1.0))
                }
            }
            .frame(height: 6)
            RFText(
                String(format: "%.0f%%", value),
                style: .caption,
                color: RFColors.fallbackTextSecondary
            )
            .frame(width: 36, alignment: .trailing)
        }
    }

    // MARK: - Error Banner

    private func errorBanner(message: String) -> some View {
        VStack {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.white)
                RFText(message, style: .body, color: .white)
                Spacer()
                Button {
                    self.errorMessage = nil
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

    // MARK: - Projects Section

    private var projectsSection: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                RFText(
                    String(localized: "agent.projects.title"),
                    style: .headline
                )

                ForEach(agentProjects) { project in
                    HStack {
                        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                            RFText(project.projectName, style: .body)
                            if !project.techStack.isEmpty {
                                RFText(
                                    project.techStack.joined(separator: ", "),
                                    style: .caption,
                                    color: RFColors.fallbackTextTertiary
                                )
                            }
                        }
                        Spacer()
                        Toggle("", isOn: Binding(
                            get: { project.isActive },
                            set: { newValue in
                                Task {
                                    await toggleProjectActive(project: project, isActive: newValue)
                                }
                            }
                        ))
                        .labelsHidden()
                        .tint(RFColors.fallbackPrimary)
                    }

                    if project.id != agentProjects.last?.id {
                        Divider()
                    }
                }
            }
        }
    }

    // MARK: - Claude Processes Section

    private var claudeProcessesSection: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                HStack {
                    RFText(
                        String(localized: "agent.processes.title"),
                        style: .headline
                    )
                    Spacer()
                    RFText(
                        "\(claudeProcesses.count)",
                        style: .captionBold,
                        color: RFColors.fallbackPrimary
                    )
                    .padding(.horizontal, RFSpacing.sm)
                    .padding(.vertical, RFSpacing.xxs)
                    .background(RFColors.fallbackPrimary.opacity(0.1))
                    .clipShape(Capsule())
                }

                ForEach(claudeProcesses) { process in
                    HStack(spacing: RFSpacing.sm) {
                        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                            RFText("PID: \(process.pid)", style: .captionBold)
                            if let cmdline = process.cmdline {
                                RFText(cmdline, style: .caption, color: RFColors.fallbackTextTertiary)
                                    .lineLimit(1)
                            }
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: RFSpacing.xxs) {
                            HStack(spacing: RFSpacing.xxs) {
                                Image(systemName: "cpu")
                                    .font(.caption2)
                                    .foregroundStyle(barColor(for: process.cpuPercent))
                                RFText(
                                    String(format: "%.1f%%", process.cpuPercent),
                                    style: .caption,
                                    color: barColor(for: process.cpuPercent)
                                )
                            }
                            HStack(spacing: RFSpacing.xxs) {
                                Image(systemName: "memorychip")
                                    .font(.caption2)
                                    .foregroundStyle(RFColors.fallbackTextSecondary)
                                RFText(
                                    String(format: "%.0f MB", process.memoryMb),
                                    style: .caption,
                                    color: RFColors.fallbackTextSecondary
                                )
                            }
                        }
                    }

                    if process.id != claudeProcesses.last?.id {
                        Divider()
                    }
                }
            }
        }
    }

    // MARK: - Data Loading

    private func loadUsage() async {
        isRefreshing = true
        do {
            subscriptionUsage = try await getUsageUseCase.execute()
        } catch {
            errorMessage = String(localized: "agent.subscription.loadError")
        }
        isRefreshing = false
    }

    private func loadProjects() async {
        do {
            agentProjects = try await getAgentProjectsUseCase.execute(agentId: agent.hostId)
        } catch {
            // Sessizce yoksay — detay ekraninda hata mesaji gerekmez
        }
    }

    private func loadProcesses() async {
        do {
            claudeProcesses = try await getClaudeProcessesUseCase.execute(agentId: agent.hostId)
        } catch {
            // Sessizce yoksay
        }
    }

    private func toggleProjectActive(project: AgentProject, isActive: Bool) async {
        do {
            let updated = try await setProjectActiveUseCase.execute(
                agentId: agent.hostId,
                projectId: project.projectId,
                isActive: isActive
            )
            if let index = agentProjects.firstIndex(where: { $0.projectId == project.projectId }) {
                agentProjects[index] = updated
            }
        } catch {
            errorMessage = String(localized: "agent.projects.toggleError")
        }
    }

    private func refreshUsage() async {
        isRefreshing = true
        do {
            subscriptionUsage = try await refreshUsageUseCase.execute()
        } catch {
            errorMessage = String(localized: "agent.subscription.loadError")
        }
        isRefreshing = false
    }

    // MARK: - Helpers

    private func capabilityLabel(_ capability: AgentCapability) -> String {
        switch capability {
        case .docker: return "Docker"
        case .playwright: return "Playwright"
        case .maestroIos: return "Maestro iOS"
        case .maestroAndroid: return "Maestro Android"
        case .shell: return "Shell"
        case .xcodeBuild: return "Xcode"
        case .androidBuild: return "Android"
        case .git: return "Git"
        case .python: return "Python"
        case .nodejs: return "Node.js"
        }
    }

    private func barColor(for value: Double) -> Color {
        if value >= 90 { return RFColors.error }
        if value >= 70 { return RFColors.warning }
        return RFColors.success
    }

    private func formatUptime(_ seconds: Int) -> String {
        let hours = seconds / 3600
        let minutes = (seconds % 3600) / 60
        if hours > 0 {
            return "\(hours)h \(minutes)m"
        }
        return "\(minutes)m"
    }

    private func relativeTime(from date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return formatter.localizedString(for: date, relativeTo: Date())
    }

    private func shortDay(_ dateString: String) -> String {
        // "2026-03-04" -> "04"
        String(dateString.suffix(2))
    }
}

#Preview {
    NavigationStack {
        AgentDetailView(
            agent: Agent(
                hostId: "macbook-pro",
                status: .online,
                capabilities: [.shell, .docker, .git, .python],
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
            getUsageUseCase: GetSubscriptionUsageUseCase(
                repository: PreviewAgentRepository()
            ),
            refreshUsageUseCase: RefreshSubscriptionUsageUseCase(
                repository: PreviewAgentRepository()
            ),
            getAgentProjectsUseCase: GetAgentProjectsUseCase(
                repository: PreviewAgentRepository()
            ),
            setProjectActiveUseCase: SetProjectActiveUseCase(
                repository: PreviewAgentRepository()
            ),
            getClaudeProcessesUseCase: GetClaudeProcessesUseCase(
                repository: PreviewAgentRepository()
            )
        )
    }
}
