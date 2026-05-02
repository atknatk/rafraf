import Charts
import Factory
import SwiftUI

/// Agent detay ekrani.
/// Agent bilgileri ve Claude Max subscription kullanim durumunu gosterir.
struct AgentDetailView: View {
    let agent: Agent
    @State private var subscriptionUsage: SubscriptionUsage?
    @State private var agentProjects: [AgentProject] = []
    @State private var claudeProcesses: [ClaudeProcess] = []
    @State private var agentTasks: [AgentTask] = []
    @State private var pendingTaskCount = 0
    @State private var isRefreshing = false
    @State private var isRescanning = false
    @State private var errorMessage: String?
    @State private var showDispatchTask = false
    @State private var processPollingTask: Task<Void, Never>?
    @State private var skipPermissions: Bool = false
    @State private var showSubagentTree = false
    @State private var subagentSnapshot: [Subagent] = []
    @State private var subagentObserveTask: Task<Void, Never>?

    private let getUsageUseCase: GetSubscriptionUsageUseCase
    private let refreshUsageUseCase: RefreshSubscriptionUsageUseCase
    private let getAgentProjectsUseCase: GetAgentProjectsUseCase
    private let setProjectActiveUseCase: SetProjectActiveUseCase
    private let getClaudeProcessesUseCase: GetClaudeProcessesUseCase
    private let getAgentTasksUseCase: GetAgentTasksUseCase
    private let cancelAgentTaskUseCase: CancelAgentTaskUseCase
    private let dispatchAgentTaskUseCase: DispatchAgentTaskUseCase
    private let rescanProjectsUseCase: RescanProjectsUseCase
    private let getSkipPermissionsUseCase: GetAgentSkipPermissionsUseCase
    private let updateSettingsUseCase: UpdateAgentSettingsUseCase

    init(
        agent: Agent,
        getUsageUseCase: GetSubscriptionUsageUseCase,
        refreshUsageUseCase: RefreshSubscriptionUsageUseCase,
        getAgentProjectsUseCase: GetAgentProjectsUseCase,
        setProjectActiveUseCase: SetProjectActiveUseCase,
        getClaudeProcessesUseCase: GetClaudeProcessesUseCase,
        getAgentTasksUseCase: GetAgentTasksUseCase,
        cancelAgentTaskUseCase: CancelAgentTaskUseCase,
        dispatchAgentTaskUseCase: DispatchAgentTaskUseCase,
        rescanProjectsUseCase: RescanProjectsUseCase,
        getSkipPermissionsUseCase: GetAgentSkipPermissionsUseCase,
        updateSettingsUseCase: UpdateAgentSettingsUseCase
    ) {
        self.agent = agent
        self.getUsageUseCase = getUsageUseCase
        self.refreshUsageUseCase = refreshUsageUseCase
        self.getAgentProjectsUseCase = getAgentProjectsUseCase
        self.setProjectActiveUseCase = setProjectActiveUseCase
        self.getClaudeProcessesUseCase = getClaudeProcessesUseCase
        self.getAgentTasksUseCase = getAgentTasksUseCase
        self.cancelAgentTaskUseCase = cancelAgentTaskUseCase
        self.dispatchAgentTaskUseCase = dispatchAgentTaskUseCase
        self.rescanProjectsUseCase = rescanProjectsUseCase
        self.getSkipPermissionsUseCase = getSkipPermissionsUseCase
        self.updateSettingsUseCase = updateSettingsUseCase
    }

    var body: some View {
        ScrollView {
            VStack(spacing: RFSpacing.md) {
                agentInfoSection
                settingsSection
                if !agentTasks.isEmpty {
                    tasksSection
                }
                subagentsSection
                if !activeProjects.isEmpty || !discoveredProjects.isEmpty {
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
        .sheet(isPresented: $showDispatchTask, onDismiss: {
            Task { await loadTasks() }
        }) {
            DispatchTaskSheet(
                agentId: agent.hostId,
                dispatchUseCase: dispatchAgentTaskUseCase
            )
        }
        .sheet(isPresented: $showSubagentTree) {
            NavigationStack {
                SubagentTreeView(
                    sessionId: nil,
                    viewModel: Container.shared.subagentTreeViewModel()
                )
            }
            .presentationDetents([.large])
            .presentationDragIndicator(.visible)
        }
        .task {
            async let usageTask: () = loadUsage()
            async let projectsTask: () = loadProjects()
            async let processesTask: () = loadProcesses()
            async let tasksTask: () = loadTasks()
            async let skipTask: () = loadSkipPermissions()
            _ = await (usageTask, projectsTask, processesTask, tasksTask, skipTask)
            startProcessPolling()
            startSubagentObserving()
        }
        .onDisappear {
            processPollingTask?.cancel()
            processPollingTask = nil
            subagentObserveTask?.cancel()
            subagentObserveTask = nil
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
                    if agent.status == .online || agent.status == .busy {
                        RFButton(
                            String(localized: "agent.task.dispatch"),
                            style: .primary,
                            size: .small
                        ) {
                            showDispatchTask = true
                        }
                    }
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

    // MARK: - Settings Section

    private var settingsSection: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                RFText(String(localized: "agent.settings.title"), style: .headline)

                HStack {
                    VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                        RFText(
                            String(localized: "agent.settings.skipPermissions"),
                            style: .body
                        )
                        RFText(
                            String(localized: "agent.settings.skipPermissions.subtitle"),
                            style: .caption,
                            color: RFColors.fallbackTextSecondary
                        )
                    }
                    Spacer()
                    Toggle("", isOn: Binding(
                        get: { skipPermissions },
                        set: { newValue in
                            Task { await toggleSkipPermissions(newValue) }
                        }
                    ))
                    .labelsHidden()
                    .tint(RFColors.warning)
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
                    .fill(usageStatusColor(usage))
                    .frame(width: 8, height: 8)
                RFText(
                    usageStatusText(usage),
                    style: .caption,
                    color: usageStatusColor(usage)
                )
            }
        }

        // Usage progress bar
        if usage.dailyMessageLimit > 0 {
            usageProgressBar(usage)
        }

        // Warning / limit exceeded banner
        if usage.limitExceeded || usage.isRateLimited {
            HStack(spacing: RFSpacing.xs) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.white)
                    .font(.caption)
                RFText(
                    String(localized: "agent.subscription.limitExceeded"),
                    style: .captionBold,
                    color: .white
                )
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, RFSpacing.xs)
            .padding(.horizontal, RFSpacing.sm)
            .background(RFColors.error)
            .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.small))
        } else if usage.warningThresholdReached {
            HStack(spacing: RFSpacing.xs) {
                Image(systemName: "exclamationmark.circle.fill")
                    .foregroundStyle(RFColors.warning)
                    .font(.caption)
                RFText(
                    String(localized: "agent.subscription.warningThreshold"),
                    style: .captionBold,
                    color: RFColors.warning
                )
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, RFSpacing.xs)
            .padding(.horizontal, RFSpacing.sm)
            .background(RFColors.warning.opacity(0.15))
            .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.small))
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

    // MARK: - Weekly Chart (Swift Charts)

    private func weeklyChart(days: [DailyUsageStats]) -> some View {
        Chart(days) { day in
            BarMark(
                x: .value("Day", shortDay(day.date)),
                y: .value("Messages", day.messageCount)
            )
            .foregroundStyle(
                LinearGradient(
                    colors: [RFColors.fallbackPrimary, RFColors.fallbackPrimary.opacity(0.5)],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
            .cornerRadius(3)
        }
        .chartXAxis {
            AxisMarks(values: .automatic) { _ in
                AxisValueLabel()
                    .font(.system(size: 9))
                    .foregroundStyle(RFColors.fallbackTextTertiary)
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) { _ in
                AxisValueLabel()
                    .font(.system(size: 9))
                    .foregroundStyle(RFColors.fallbackTextTertiary)
                AxisGridLine()
                    .foregroundStyle(RFColors.fallbackSurface)
            }
        }
        .frame(height: 100)
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

    private var activeProjects: [AgentProject] { agentProjects.filter(\.isActive) }
    private var discoveredProjects: [AgentProject] { agentProjects.filter { !$0.isActive } }

    private var rescanButton: some View {
        Button {
            Task { await triggerRescan() }
        } label: {
            HStack(spacing: RFSpacing.xxs) {
                if isRescanning {
                    ProgressView().controlSize(.mini)
                } else {
                    Image(systemName: "arrow.clockwise")
                        .font(.caption.weight(.semibold))
                }
                RFText(
                    isRescanning
                        ? String(localized: "agent.projects.rescanning")
                        : String(localized: "agent.projects.rescan"),
                    style: .captionBold,
                    color: RFColors.fallbackPrimary
                )
            }
            .padding(.horizontal, RFSpacing.sm)
            .padding(.vertical, RFSpacing.xxs)
            .background(RFColors.fallbackPrimary.opacity(0.08))
            .clipShape(Capsule())
        }
        .buttonStyle(.plain)
        .disabled(isRescanning || agent.status == .offline)
    }

    private var projectsSection: some View {
        VStack(spacing: RFSpacing.sm) {
            if !activeProjects.isEmpty {
                RFCard {
                    VStack(alignment: .leading, spacing: RFSpacing.sm) {
                        HStack {
                            Circle()
                                .fill(RFColors.success)
                                .frame(width: 8, height: 8)
                            RFText(
                                String(localized: "agent.projects.active"),
                                style: .headline
                            )
                            Spacer()
                            rescanButton
                        }

                        ForEach(activeProjects) { project in
                            projectRow(project: project)
                            if project.id != activeProjects.last?.id {
                                Divider()
                            }
                        }
                    }
                }
            }

            if !discoveredProjects.isEmpty {
                RFCard {
                    VStack(alignment: .leading, spacing: RFSpacing.sm) {
                        HStack {
                            Circle()
                                .fill(RFColors.fallbackTextTertiary)
                                .frame(width: 8, height: 8)
                            RFText(
                                String(localized: "agent.projects.discovered"),
                                style: .headline,
                                color: RFColors.fallbackTextSecondary
                            )
                            Spacer()
                            if activeProjects.isEmpty {
                                rescanButton
                            }
                        }

                        ForEach(discoveredProjects) { project in
                            projectRow(project: project)
                            if project.id != discoveredProjects.last?.id {
                                Divider()
                            }
                        }
                    }
                }
                .opacity(0.85)
            }
        }
    }

    @ViewBuilder
    private func projectRow(project: AgentProject) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                RFText(project.projectName, style: .body)
                if let localPath = project.localPath {
                    RFText(
                        shortPath(localPath),
                        style: .caption,
                        color: RFColors.fallbackTextSecondary
                    )
                }
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
    }

    /// "/Users/atakan/Projects/rafraf" -> "Projects/rafraf"
    private func shortPath(_ path: String) -> String {
        let components = path.split(separator: "/").map(String.init)
        guard components.count >= 2 else { return path }
        return components.suffix(2).joined(separator: "/")
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

    // MARK: - Tasks Section

    private var tasksSection: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                HStack {
                    RFText(String(localized: "agent.tasks.title"), style: .headline)
                    Spacer()
                    if pendingTaskCount > 0 {
                        RFText(
                            "\(pendingTaskCount) \(String(localized: "agent.tasks.pending"))",
                            style: .captionBold,
                            color: RFColors.warning
                        )
                        .padding(.horizontal, RFSpacing.sm)
                        .padding(.vertical, RFSpacing.xxs)
                        .background(RFColors.warning.opacity(0.1))
                        .clipShape(Capsule())
                    }
                    RFButton(String(localized: "agent.tasks.refresh"), style: .ghost, size: .small) {
                        Task { await loadTasks() }
                    }
                }

                ForEach(agentTasks.prefix(10)) { task in
                    taskRow(task)
                    if task.id != agentTasks.prefix(10).last?.id {
                        Divider()
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func taskRow(_ task: AgentTask) -> some View {
        HStack(spacing: RFSpacing.sm) {
            taskStatusIcon(task.status)

            VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                HStack(spacing: RFSpacing.xs) {
                    RFText(task.runner, style: .captionBold)
                        .padding(.horizontal, RFSpacing.xs)
                        .padding(.vertical, 2)
                        .background(RFColors.fallbackSurface)
                        .clipShape(Capsule())
                    RFText(task.action, style: .body)
                        .lineLimit(1)
                }
                if let error = task.error {
                    RFText(error, style: .caption, color: RFColors.error)
                        .lineLimit(2)
                }
            }

            Spacer()

            VStack(alignment: .trailing, spacing: RFSpacing.xxs) {
                if let duration = task.durationText {
                    RFText(duration, style: .caption, color: RFColors.fallbackTextTertiary)
                }
                if task.status.isCancellable {
                    Button {
                        Task { await cancelTask(task) }
                    } label: {
                        Image(systemName: "xmark.circle")
                            .foregroundStyle(RFColors.error)
                            .font(.system(size: 18))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.vertical, RFSpacing.xxs)
    }

    @ViewBuilder
    private func taskStatusIcon(_ status: AgentTaskStatus) -> some View {
        let (icon, color): (String, Color) = switch status {
        case .pending: ("clock", RFColors.fallbackTextTertiary)
        case .running: ("arrow.trianglehead.2.clockwise", RFColors.fallbackPrimary)
        case .completed: ("checkmark.circle.fill", RFColors.success)
        case .failed: ("xmark.circle.fill", RFColors.error)
        case .cancelled: ("minus.circle.fill", RFColors.fallbackTextTertiary)
        case .timeout: ("timer", RFColors.warning)
        }
        Image(systemName: icon)
            .foregroundStyle(color)
            .font(.system(size: 16))
            .frame(width: 20)
    }

    // MARK: - Subagents Section (T1.7 — Doc 10 §6.3.3)

    /// Claude Agent Teams subagent ozet karti.
    /// Subagent yoksa kart gosterilmez. Aksi halde count + son aktivite +
    /// "Detay" butonu ile SubagentTreeView sheet'ini acar.
    @ViewBuilder
    private var subagentsSection: some View {
        if !subagentSnapshot.isEmpty {
            RFCard {
                VStack(alignment: .leading, spacing: RFSpacing.sm) {
                    HStack {
                        Image(systemName: "person.2.gobackward")
                            .foregroundStyle(RFColors.fallbackPrimary)
                        RFText(
                            String(localized: "agent.subagents.title"),
                            style: .headline
                        )
                        Spacer()
                        RFText(
                            "\(subagentSnapshot.count)",
                            style: .captionBold,
                            color: RFColors.fallbackPrimary
                        )
                        .padding(.horizontal, RFSpacing.sm)
                        .padding(.vertical, RFSpacing.xxs)
                        .background(RFColors.fallbackPrimary.opacity(0.1))
                        .clipShape(Capsule())
                    }

                    HStack(spacing: RFSpacing.md) {
                        subagentStatusCount(
                            label: String(localized: "agent.subagent.status.inProgress"),
                            count: subagentSnapshot.filter { $0.status == .inProgress || $0.status == .spawned }.count,
                            color: RFColors.fallbackPrimary
                        )
                        subagentStatusCount(
                            label: String(localized: "agent.subagent.status.completed"),
                            count: subagentSnapshot.filter { $0.status == .completed }.count,
                            color: RFColors.success
                        )
                        subagentStatusCount(
                            label: String(localized: "agent.subagent.status.failed"),
                            count: subagentSnapshot.filter { $0.status == .failed }.count,
                            color: RFColors.error
                        )
                    }

                    RFButton(
                        String(localized: "agent.subagents.viewTree"),
                        style: .ghost,
                        size: .small
                    ) {
                        showSubagentTree = true
                    }
                    .accessibilityHint(String(localized: "agent.subagents.viewTree.hint"))
                }
            }
        }
    }

    private func subagentStatusCount(label: String, count: Int, color: Color) -> some View {
        VStack(spacing: RFSpacing.xxs) {
            RFText("\(count)", style: .headline, color: color)
            RFText(label, style: .caption, color: RFColors.fallbackTextSecondary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity)
    }

    private func startSubagentObserving() {
        subagentObserveTask?.cancel()
        let repository = Container.shared.subagentRepository()
        subagentObserveTask = Task { @MainActor in
            let stream = await repository.observeAllSubagents()
            for await snapshot in stream {
                guard !Task.isCancelled else { return }
                self.subagentSnapshot = snapshot
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

    private func startProcessPolling() {
        processPollingTask?.cancel()
        processPollingTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                guard !Task.isCancelled else { break }
                await loadProcesses()
            }
        }
    }

    private func triggerRescan() async {
        isRescanning = true
        do {
            try await rescanProjectsUseCase.execute(agentId: agent.hostId)
            try? await Task.sleep(for: .seconds(2))
            await loadProjects()
        } catch {
            errorMessage = String(localized: "agent.projects.rescanError")
        }
        isRescanning = false
    }

    private func loadTasks() async {
        do {
            let result = try await getAgentTasksUseCase.execute(agentId: agent.hostId)
            agentTasks = result.tasks
            pendingTaskCount = result.pendingCount
        } catch {
            // Sessizce yoksay — tasks not critical
        }
    }

    private func cancelTask(_ task: AgentTask) async {
        do {
            try await cancelAgentTaskUseCase.execute(agentId: agent.hostId, taskId: task.id)
            await loadTasks()
        } catch {
            errorMessage = String(localized: "agent.tasks.cancelError")
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

    private func loadSkipPermissions() async {
        do {
            skipPermissions = try await getSkipPermissionsUseCase.execute(agentId: agent.hostId)
        } catch {
            // Sessizce yoksay — default false kalir
        }
    }

    private func toggleSkipPermissions(_ value: Bool) async {
        skipPermissions = value
        do {
            try await updateSettingsUseCase.execute(
                agentId: agent.hostId,
                dangerouslySkipPermissions: value
            )
        } catch {
            skipPermissions = !value
            errorMessage = String(localized: "agent.settings.updateError")
        }
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

    // MARK: - Usage Progress Bar

    private func usageProgressBar(_ usage: SubscriptionUsage) -> some View {
        VStack(spacing: RFSpacing.xxs) {
            HStack {
                RFText(
                    String(localized: "agent.subscription.dailyUsage"),
                    style: .caption,
                    color: RFColors.fallbackTextSecondary
                )
                Spacer()
                let totalMessages = usage.todayUsage.messageCount + usage.totalMessagesToday
                RFText(
                    "\(totalMessages)/\(usage.dailyMessageLimit)",
                    style: .captionBold,
                    color: usageBarColor(usage.usagePercent)
                )
            }
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: RFCornerRadius.small)
                        .fill(RFColors.fallbackSurface)
                    RoundedRectangle(cornerRadius: RFCornerRadius.small)
                        .fill(usageBarColor(usage.usagePercent))
                        .frame(width: geometry.size.width * min(usage.usagePercent / 100.0, 1.0))
                        .animation(.easeInOut(duration: 0.3), value: usage.usagePercent)
                }
            }
            .frame(height: 8)

            HStack {
                RFText(
                    String(format: "%.0f%%", usage.usagePercent),
                    style: .caption,
                    color: usageBarColor(usage.usagePercent)
                )
                Spacer()
            }
        }
    }

    private func usageBarColor(_ percent: Double) -> Color {
        if percent >= 100 { return RFColors.error }
        if percent >= 80 { return RFColors.warning }
        return RFColors.success
    }

    private func usageStatusColor(_ usage: SubscriptionUsage) -> Color {
        if usage.isRateLimited || usage.limitExceeded { return RFColors.error }
        if usage.warningThresholdReached { return RFColors.warning }
        return RFColors.success
    }

    private func usageStatusText(_ usage: SubscriptionUsage) -> String {
        if usage.isRateLimited {
            return String(localized: "agent.subscription.rateLimited")
        }
        if usage.limitExceeded {
            return String(localized: "agent.subscription.limitExceeded")
        }
        if usage.warningThresholdReached {
            return String(localized: "agent.subscription.warningThreshold")
        }
        return String(localized: "agent.subscription.normal")
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

// MARK: - Dispatch Task Sheet

/// Agent'a gorev gonderme formu.
private struct DispatchTaskSheet: View {
    let agentId: String
    let dispatchUseCase: DispatchAgentTaskUseCase

    @Environment(\.dismiss) private var dismiss
    @State private var selectedRunner = "shell"
    @State private var action = ""
    @State private var command = ""
    @State private var isSending = false
    @State private var errorMessage: String?

    private let runners = ["shell", "docker", "playwright", "maestro"]

    var body: some View {
        NavigationStack {
            Form {
                Section(String(localized: "agent.task.runner")) {
                    Picker(String(localized: "agent.task.runner"), selection: $selectedRunner) {
                        ForEach(runners, id: \.self) { runner in
                            Text(runner.capitalized).tag(runner)
                        }
                    }
                    .pickerStyle(.segmented)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets(top: 8, leading: 0, bottom: 8, trailing: 0))
                }

                Section(String(localized: "agent.task.action")) {
                    TextField(runnerActionPlaceholder, text: $action)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                }

                Section(String(localized: "agent.task.command")) {
                    TextField(String(localized: "agent.task.command.placeholder"), text: $command)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .font(.system(.body, design: .monospaced))
                }

                if let error = errorMessage {
                    Section {
                        RFText(error, style: .caption, color: RFColors.error)
                    }
                }
            }
            .navigationTitle(String(localized: "agent.task.dispatch"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(String(localized: "agent.action.cancel")) {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(String(localized: "agent.task.send")) {
                        Task { await sendTask() }
                    }
                    .disabled(action.isEmpty || isSending)
                    .fontWeight(.semibold)
                }
            }
            .overlay {
                if isSending {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(Color.black.opacity(0.1))
                }
            }
        }
    }

    private var runnerActionPlaceholder: String {
        switch selectedRunner {
        case "shell": return "run_command"
        case "docker": return "up / down / build"
        case "playwright": return "take_screenshot"
        case "maestro": return "run_flow"
        default: return "action"
        }
    }

    private func sendTask() async {
        isSending = true
        errorMessage = nil
        var params: [String: String] = [:]
        if !command.isEmpty {
            params["command"] = command
        }
        do {
            try await dispatchUseCase.execute(
                agentId: agentId,
                runner: selectedRunner,
                action: action.isEmpty ? runnerActionPlaceholder : action,
                params: params
            )
            HapticManager.success()
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
            HapticManager.error()
        }
        isSending = false
    }
}

#Preview {
    let repo = PreviewAgentRepository()
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
                ),
                dangerouslySkipPermissions: false
            ),
            getUsageUseCase: GetSubscriptionUsageUseCase(repository: repo),
            refreshUsageUseCase: RefreshSubscriptionUsageUseCase(repository: repo),
            getAgentProjectsUseCase: GetAgentProjectsUseCase(repository: repo),
            setProjectActiveUseCase: SetProjectActiveUseCase(repository: repo),
            getClaudeProcessesUseCase: GetClaudeProcessesUseCase(repository: repo),
            getAgentTasksUseCase: GetAgentTasksUseCase(repository: repo),
            cancelAgentTaskUseCase: CancelAgentTaskUseCase(repository: repo),
            dispatchAgentTaskUseCase: DispatchAgentTaskUseCase(repository: repo),
            rescanProjectsUseCase: RescanProjectsUseCase(repository: repo),
            getSkipPermissionsUseCase: GetAgentSkipPermissionsUseCase(repository: repo),
            updateSettingsUseCase: UpdateAgentSettingsUseCase(repository: repo)
        )
    }
}
