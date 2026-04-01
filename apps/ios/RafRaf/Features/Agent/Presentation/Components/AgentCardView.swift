import SwiftUI

/// Agent kart bileseni.
/// Agent durumunu, yeteneklerini ve kaynak kullanimini gosterir.
struct AgentCardView: View {
    let agent: Agent

    var body: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                headerRow
                capabilityTags
                if let resources = agent.resources {
                    resourceBars(resources)
                }
                footerRow
            }
        }
    }

    // MARK: - Header

    private var headerRow: some View {
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
    }

    // MARK: - Capabilities

    private var capabilityTags: some View {
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

    // MARK: - Footer

    private var footerRow: some View {
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
}

#Preview {
    AgentCardView(
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
        )
    )
    .padding()
}
