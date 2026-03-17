import Charts
import SwiftUI

/// Birlesik sistem durumu ekrani — backend health, agent fleet, usage, pulse.
struct SystemStatusView: View {
    private let getMonitoringUseCase: GetMonitoringDashboardUseCase

    @State private var dashboard: MonitoringDashboard?
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var autoRefreshTask: Task<Void, Never>?

    init(getMonitoringUseCase: GetMonitoringDashboardUseCase) {
        self.getMonitoringUseCase = getMonitoringUseCase
    }

    var body: some View {
        ScrollView {
            if isLoading && dashboard == nil {
                skeletonView
            } else if let dashboard {
                VStack(spacing: RFSpacing.md) {
                    systemHealthSection(dashboard.system)
                    agentFleetSection(dashboard.agents)
                    usageSection(dashboard.usage)
                    if let pulse = dashboard.pulse {
                        pulseSection(pulse)
                    }
                }
                .padding(.horizontal, RFSpacing.md)
                .padding(.vertical, RFSpacing.sm)
            } else if let errorMessage {
                errorView(errorMessage)
            }
        }
        .background(RFColors.fallbackBackground)
        .navigationTitle(String(localized: "monitoring.title"))
        .navigationBarTitleDisplayMode(.large)
        .refreshable { await loadDashboard() }
        .task {
            await loadDashboard()
            startAutoRefresh()
        }
        .onDisappear {
            autoRefreshTask?.cancel()
            autoRefreshTask = nil
        }
    }

    // MARK: - System Health Section

    private func systemHealthSection(_ system: SystemHealth) -> some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                HStack {
                    RFText(String(localized: "monitoring.system.title"), style: .headline)
                    Spacer()
                    statusBadge(system.status)
                }

                // Component status pills
                FlowLayout(spacing: RFSpacing.xxs) {
                    ForEach(system.components) { component in
                        componentPill(component)
                    }
                }

                Divider()

                // Server metrics
                HStack(spacing: RFSpacing.md) {
                    metricCard(
                        icon: "cpu",
                        label: "CPU",
                        value: String(format: "%.1f%%", system.cpuPercent),
                        color: barColor(for: system.cpuPercent)
                    )
                    metricCard(
                        icon: "memorychip",
                        label: String(localized: "monitoring.system.memory"),
                        value: String(format: "%.0f MB", system.memoryUsedMb),
                        color: barColor(for: system.memoryPercent)
                    )
                    metricCard(
                        icon: "clock",
                        label: String(localized: "monitoring.system.uptime"),
                        value: formatUptime(system.uptimeSeconds),
                        color: RFColors.fallbackPrimary
                    )
                }
            }
        }
    }

    // MARK: - Agent Fleet Section

    private func agentFleetSection(_ agents: AgentFleetOverview) -> some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                HStack {
                    RFText(String(localized: "monitoring.agents.title"), style: .headline)
                    Spacer()
                    HStack(spacing: RFSpacing.xs) {
                        agentCountBadge(count: agents.online, color: RFColors.success, label: "Online")
                        if agents.busy > 0 {
                            agentCountBadge(count: agents.busy, color: RFColors.warning, label: "Busy")
                        }
                        if agents.offline > 0 {
                            agentCountBadge(count: agents.offline, color: RFColors.error, label: "Offline")
                        }
                    }
                }

                if agents.agents.isEmpty {
                    RFText(
                        String(localized: "monitoring.agents.noAgents"),
                        style: .body,
                        color: RFColors.fallbackTextSecondary
                    )
                } else {
                    ForEach(agents.agents) { agent in
                        agentRow(agent)
                        if agent.id != agents.agents.last?.id {
                            Divider()
                        }
                    }
                }
            }
        }
    }

    // MARK: - Usage Section

    private func usageSection(_ usage: UsageOverview) -> some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                HStack {
                    RFText(String(localized: "monitoring.usage.title"), style: .headline)
                    Spacer()
                    RFText(
                        usage.subscriptionType.uppercased(),
                        style: .captionBold,
                        color: .white
                    )
                    .padding(.horizontal, RFSpacing.sm)
                    .padding(.vertical, RFSpacing.xxs)
                    .background(RFColors.brandGradient)
                    .clipShape(Capsule())
                }

                // Usage progress bar
                if usage.dailyMessageLimit > 0 {
                    VStack(spacing: RFSpacing.xxs) {
                        HStack {
                            RFText(
                                String(localized: "monitoring.usage.daily"),
                                style: .caption,
                                color: RFColors.fallbackTextSecondary
                            )
                            Spacer()
                            RFText(
                                "\(usage.totalMessagesToday)/\(usage.dailyMessageLimit)",
                                style: .captionBold,
                                color: usageColor(usage.usagePercent)
                            )
                        }
                        GeometryReader { geometry in
                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: RFCornerRadius.small)
                                    .fill(RFColors.fallbackSurface)
                                RoundedRectangle(cornerRadius: RFCornerRadius.small)
                                    .fill(usageColor(usage.usagePercent))
                                    .frame(width: geometry.size.width * min(usage.usagePercent / 100.0, 1.0))
                                    .animation(.easeInOut(duration: 0.3), value: usage.usagePercent)
                            }
                        }
                        .frame(height: 8)
                        HStack {
                            RFText(
                                String(format: "%.0f%%", usage.usagePercent),
                                style: .captionBold,
                                color: usageColor(usage.usagePercent)
                            )
                            Spacer()
                            if usage.isRateLimited {
                                HStack(spacing: RFSpacing.xxs) {
                                    Circle().fill(RFColors.error).frame(width: 6, height: 6)
                                    RFText(
                                        String(localized: "monitoring.usage.rateLimited"),
                                        style: .caption,
                                        color: RFColors.error
                                    )
                                }
                            }
                        }
                    }
                }

                // Warning banner
                if usage.limitExceeded || usage.isRateLimited {
                    alertBanner(
                        icon: "exclamationmark.triangle.fill",
                        text: String(localized: "agent.subscription.limitExceeded"),
                        bgColor: RFColors.error
                    )
                } else if usage.warningThresholdReached {
                    alertBanner(
                        icon: "exclamationmark.circle.fill",
                        text: String(localized: "agent.subscription.warningThreshold"),
                        bgColor: RFColors.warning.opacity(0.15),
                        textColor: RFColors.warning
                    )
                }
            }
        }
    }

    // MARK: - Pulse Section

    private func pulseSection(_ pulse: PulseSummary) -> some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                HStack {
                    RFText(String(localized: "monitoring.pulse.title"), style: .headline)
                    Spacer()
                    if !pulse.reportDate.isEmpty {
                        RFText(pulse.reportDate, style: .caption, color: RFColors.fallbackTextTertiary)
                    }
                }

                if !pulse.summaryText.isEmpty {
                    RFText(pulse.summaryText, style: .body, color: RFColors.fallbackTextSecondary)
                }

                // Stats row
                HStack(spacing: RFSpacing.md) {
                    metricCard(
                        icon: "message",
                        label: String(localized: "monitoring.pulse.messages"),
                        value: "\(pulse.totalMessages)",
                        color: RFColors.fallbackPrimary
                    )
                    if let cost = pulse.totalCostUsd {
                        metricCard(
                            icon: "dollarsign.circle",
                            label: String(localized: "monitoring.pulse.cost"),
                            value: String(format: "$%.2f", cost),
                            color: RFColors.info
                        )
                    }
                }

                // Risks
                if !pulse.risks.isEmpty {
                    VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                        RFText(String(localized: "monitoring.pulse.risks"), style: .captionBold, color: RFColors.error)
                        ForEach(pulse.risks, id: \.self) { risk in
                            HStack(alignment: .top, spacing: RFSpacing.xxs) {
                                Image(systemName: "exclamationmark.circle.fill")
                                    .font(.caption2)
                                    .foregroundStyle(RFColors.error)
                                RFText(risk, style: .caption, color: RFColors.fallbackTextSecondary)
                            }
                        }
                    }
                }

                // Suggestions
                if !pulse.suggestions.isEmpty {
                    VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                        RFText(
                            String(localized: "monitoring.pulse.suggestions"),
                            style: .captionBold,
                            color: RFColors.success
                        )
                        ForEach(pulse.suggestions, id: \.self) { suggestion in
                            HStack(alignment: .top, spacing: RFSpacing.xxs) {
                                Image(systemName: "lightbulb.fill")
                                    .font(.caption2)
                                    .foregroundStyle(RFColors.success)
                                RFText(suggestion, style: .caption, color: RFColors.fallbackTextSecondary)
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: - Reusable Components

    private func statusBadge(_ status: SystemStatus) -> some View {
        let (text, color): (String, Color) = switch status {
        case .healthy: (String(localized: "monitoring.status.healthy"), RFColors.success)
        case .degraded: (String(localized: "monitoring.status.degraded"), RFColors.warning)
        case .unhealthy: (String(localized: "monitoring.status.unhealthy"), RFColors.error)
        }
        return HStack(spacing: RFSpacing.xxs) {
            Circle().fill(color).frame(width: 8, height: 8)
            RFText(text, style: .captionBold, color: color)
        }
        .padding(.horizontal, RFSpacing.sm)
        .padding(.vertical, RFSpacing.xxs)
        .background(color.opacity(0.1))
        .clipShape(Capsule())
    }

    private func componentPill(_ component: ComponentHealth) -> some View {
        let isUp = component.status == "up"
        return HStack(spacing: RFSpacing.xxs) {
            Circle()
                .fill(isUp ? RFColors.success : RFColors.error)
                .frame(width: 6, height: 6)
            RFText(
                componentDisplayName(component.name),
                style: .caption,
                color: RFColors.fallbackTextSecondary
            )
            if let latency = component.latencyMs {
                RFText(
                    String(format: "%.0fms", latency),
                    style: .caption,
                    color: RFColors.fallbackTextTertiary
                )
            }
        }
        .padding(.horizontal, RFSpacing.xs)
        .padding(.vertical, RFSpacing.xxs)
        .background(RFColors.fallbackSurface)
        .clipShape(Capsule())
    }

    private func metricCard(icon: String, label: String, value: String, color: Color) -> some View {
        VStack(spacing: RFSpacing.xxs) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundStyle(color)
            RFText(value, style: .headline)
            RFText(label, style: .caption, color: RFColors.fallbackTextSecondary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity)
    }

    private func agentCountBadge(count: Int, color: Color, label: String) -> some View {
        HStack(spacing: RFSpacing.xxs) {
            Circle().fill(color).frame(width: 6, height: 6)
            RFText("\(count)", style: .captionBold, color: color)
        }
        .padding(.horizontal, RFSpacing.xs)
        .padding(.vertical, RFSpacing.xxs)
        .background(color.opacity(0.1))
        .clipShape(Capsule())
        .accessibilityLabel("\(count) \(label)")
    }

    private func agentRow(_ agent: AgentBrief) -> some View {
        HStack(spacing: RFSpacing.sm) {
            Circle()
                .fill(agent.status == "online" ? RFColors.success : agent.status == "busy" ? RFColors.warning : RFColors.error)
                .frame(width: 8, height: 8)

            VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                RFText(agent.hostId, style: .body)
                HStack(spacing: RFSpacing.sm) {
                    if agent.activeTasks > 0 {
                        RFText(
                            "\(agent.activeTasks) \(String(localized: "monitoring.agents.tasks"))",
                            style: .caption,
                            color: RFColors.fallbackTextTertiary
                        )
                    }
                    if agent.uptimeSeconds > 0 {
                        RFText(
                            formatUptime(Double(agent.uptimeSeconds)),
                            style: .caption,
                            color: RFColors.fallbackTextTertiary
                        )
                    }
                }
            }

            Spacer()

            VStack(alignment: .trailing, spacing: RFSpacing.xxs) {
                HStack(spacing: RFSpacing.xxs) {
                    Image(systemName: "cpu").font(.caption2)
                    RFText(
                        String(format: "%.0f%%", agent.cpuPercent),
                        style: .caption,
                        color: barColor(for: agent.cpuPercent)
                    )
                }
                HStack(spacing: RFSpacing.xxs) {
                    Image(systemName: "memorychip").font(.caption2)
                    RFText(
                        String(format: "%.0f%%", agent.memoryPercent),
                        style: .caption,
                        color: barColor(for: agent.memoryPercent)
                    )
                }
            }
        }
    }

    private func alertBanner(
        icon: String,
        text: String,
        bgColor: Color,
        textColor: Color = .white
    ) -> some View {
        HStack(spacing: RFSpacing.xs) {
            Image(systemName: icon)
                .foregroundStyle(textColor)
                .font(.caption)
            RFText(text, style: .captionBold, color: textColor)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, RFSpacing.xs)
        .padding(.horizontal, RFSpacing.sm)
        .background(bgColor)
        .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.small))
    }

    // MARK: - Skeleton

    private var skeletonView: some View {
        VStack(spacing: RFSpacing.md) {
            ForEach(0..<3, id: \.self) { _ in
                RoundedRectangle(cornerRadius: RFCornerRadius.medium)
                    .fill(RFColors.fallbackSurface)
                    .frame(height: 120)
            }
        }
        .padding(RFSpacing.md)
        .redacted(reason: .placeholder)
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: RFSpacing.md) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .foregroundStyle(RFColors.error)
            RFText(message, style: .body, color: RFColors.fallbackTextSecondary)
            RFButton(String(localized: "monitoring.retry"), style: .secondary, size: .medium) {
                Task { await loadDashboard() }
            }
        }
        .padding(RFSpacing.xl)
    }

    // MARK: - Helpers

    private func barColor(for value: Double) -> Color {
        if value >= 90 { return RFColors.error }
        if value >= 70 { return RFColors.warning }
        return RFColors.success
    }

    private func usageColor(_ percent: Double) -> Color {
        if percent >= 100 { return RFColors.error }
        if percent >= 80 { return RFColors.warning }
        return RFColors.success
    }

    private func formatUptime(_ seconds: Double) -> String {
        let totalSeconds = Int(seconds)
        let hours = totalSeconds / 3600
        let minutes = (totalSeconds % 3600) / 60
        if hours > 24 {
            let days = hours / 24
            return "\(days)d \(hours % 24)h"
        }
        if hours > 0 { return "\(hours)h \(minutes)m" }
        return "\(minutes)m"
    }

    private func componentDisplayName(_ name: String) -> String {
        switch name {
        case "database": return "DB"
        case "redis": return "Redis"
        case "websocket": return "WebSocket"
        case "claude_code": return "Claude CLI"
        default: return name.capitalized
        }
    }

    // MARK: - Data Loading

    private func loadDashboard() async {
        isLoading = true
        errorMessage = nil
        do {
            dashboard = try await getMonitoringUseCase.execute()
        } catch {
            if dashboard == nil {
                errorMessage = String(localized: "monitoring.loadError")
            }
        }
        isLoading = false
    }

    private func startAutoRefresh() {
        autoRefreshTask?.cancel()
        autoRefreshTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                guard !Task.isCancelled else { break }
                await loadDashboard()
            }
        }
    }
}

#Preview {
    NavigationStack {
        SystemStatusView(
            getMonitoringUseCase: GetMonitoringDashboardUseCase(
                repository: PreviewMonitoringRepository()
            )
        )
    }
}

/// Preview icin mock repository.
private final class PreviewMonitoringRepository: MonitoringRepositoryProtocol, @unchecked Sendable {
    func getDashboard() async throws -> MonitoringDashboard {
        MonitoringDashboard(
            timestamp: Date(),
            system: SystemHealth(
                status: .healthy,
                uptimeSeconds: 86400,
                startedAt: Date().addingTimeInterval(-86400),
                cpuPercent: 42,
                memoryPercent: 68,
                memoryUsedMb: 1450,
                components: [
                    ComponentHealth(name: "database", status: "up", latencyMs: 2.4, detail: nil),
                    ComponentHealth(name: "redis", status: "up", latencyMs: 0.8, detail: nil),
                    ComponentHealth(name: "websocket", status: "up", latencyMs: nil, detail: "3 connections"),
                    ComponentHealth(name: "claude_code", status: "up", latencyMs: nil, detail: nil)
                ]
            ),
            agents: AgentFleetOverview(
                total: 2,
                online: 1,
                offline: 0,
                busy: 1,
                agents: [
                    AgentBrief(hostId: "macbook-pro", status: "online", cpuPercent: 45, memoryPercent: 72, activeTasks: 0, uptimeSeconds: 7200),
                    AgentBrief(hostId: "ubuntu-server", status: "busy", cpuPercent: 85, memoryPercent: 60, activeTasks: 3, uptimeSeconds: 86400)
                ]
            ),
            usage: UsageOverview(
                subscriptionType: "max",
                usagePercent: 65,
                dailyMessageLimit: 200,
                totalMessagesToday: 130,
                isRateLimited: false,
                warningThresholdReached: false,
                limitExceeded: false
            ),
            pulse: PulseSummary(
                summaryText: "Proje aktif gelisim asamasinda. Son 24 saatte 3 yeni feature implement edildi.",
                totalMessages: 245,
                totalCostUsd: 1.23,
                reportDate: "2026-03-17",
                risks: ["Agent CPU kullanimi yuksek — 85%"],
                suggestions: ["Rate limit'e yaklasiyorsunuz, batch islemleri azaltin"]
            )
        )
    }
}
