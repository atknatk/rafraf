import SwiftUI

/// Bir session'a ait Claude Agent Teams subagent calismalarini agac (parent
/// -> children) seklinde gosteren ekran.
///
/// Doc 10 §6.3.3 — iOS Agent feature subagent tree (OutlineGroup tabanli).
/// AgentDetailView icindeki "Subagents" sheet'inden acilir.
struct SubagentTreeView: View {
    /// Hangi sessionId'ye abone olunacak. `nil` ise tum oturumlardaki
    /// subagent'lari toplu olarak gosterir (AgentDetailView icin uygun mod).
    let sessionId: String?
    @Bindable var viewModel: SubagentTreeViewModel

    init(sessionId: String?, viewModel: SubagentTreeViewModel) {
        self.sessionId = sessionId
        self.viewModel = viewModel
    }

    var body: some View {
        Group {
            if !viewModel.hasReceivedSnapshot {
                RFLoadingView(
                    message: String(localized: "agent.subagents.loading")
                )
            } else if viewModel.subagents.isEmpty {
                RFEmptyStateView(
                    systemImage: "person.2.gobackward",
                    title: String(localized: "agent.subagents.empty.title"),
                    message: String(localized: "agent.subagents.empty.message")
                )
            } else {
                treeContent
            }
        }
        .navigationTitle(String(localized: "agent.subagents.title"))
        .navigationBarTitleDisplayMode(.inline)
        .background(RFColors.fallbackBackground)
        .task(id: sessionId) {
            if let sessionId {
                viewModel.subscribe(to: sessionId)
            } else {
                viewModel.subscribeAll()
            }
        }
        .onDisappear {
            viewModel.unsubscribe()
        }
    }

    // MARK: - Tree Content

    private var treeContent: some View {
        List {
            ForEach(viewModel.tree, id: \.id) { node in
                OutlineGroup(node, children: \.children) { row in
                    SubagentRowView(node: row)
                        .listRowBackground(RFColors.fallbackSurface)
                }
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .animation(RFAnimation.springGentle, value: viewModel.subagents)
    }
}

// MARK: - Row

/// Tek bir subagent satiri — durum ikonu, isim, prompt onizleme ve
/// genisletilebilir detay.
private struct SubagentRowView: View {
    let node: SubagentNode
    @State private var isExpanded = false

    private var subagent: Subagent { node.subagent }

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xs) {
            HStack(spacing: RFSpacing.sm) {
                SubagentStatusIcon(status: subagent.status)
                    .frame(width: 24, height: 24)

                VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                    HStack(spacing: RFSpacing.xs) {
                        RFText(subagent.name, style: .bodyBold)
                            .lineLimit(1)
                        if let isolation = subagent.isolation, isolation == "worktree" {
                            isolationBadge
                        }
                        Spacer(minLength: 0)
                    }
                    if !subagent.promptPreview.isEmpty {
                        RFText(
                            subagent.promptPreview,
                            style: .caption,
                            color: RFColors.fallbackTextSecondary
                        )
                        .lineLimit(2)
                    }
                    RFText(
                        statusLabel(for: subagent.status),
                        style: .caption,
                        color: statusColor(for: subagent.status)
                    )
                }
            }
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(RFAnimation.springGentle) {
                    isExpanded.toggle()
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(accessibilityLabel)
            .accessibilityHint(String(localized: "agent.subagent.row.hint"))

            if isExpanded {
                expandedDetails
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(.vertical, RFSpacing.xxs)
    }

    // MARK: - Expanded Detail

    @ViewBuilder
    private var expandedDetails: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xs) {
            if let description = subagent.description, !description.isEmpty {
                detailRow(
                    icon: "text.alignleft",
                    label: String(localized: "agent.subagent.description"),
                    value: description
                )
            }
            if let type = subagent.subagentType, !type.isEmpty {
                detailRow(
                    icon: "person.crop.circle",
                    label: String(localized: "agent.subagent.type"),
                    value: type
                )
            }
            if let activity = subagent.activity, !activity.isEmpty {
                detailRow(
                    icon: "waveform.path.ecg",
                    label: String(localized: "agent.subagent.activity"),
                    value: activity
                )
            }
            if let summary = subagent.summary, !summary.isEmpty {
                detailRow(
                    icon: "doc.text",
                    label: String(localized: "agent.subagent.summary"),
                    value: summary
                )
            }
            if let totalTokens = subagent.totalTokens {
                detailRow(
                    icon: "circle.hexagonpath",
                    label: String(localized: "agent.subagent.tokens"),
                    value: "\(totalTokens)"
                )
            }
            if let toolUses = subagent.toolUses {
                detailRow(
                    icon: "wrench.and.screwdriver",
                    label: String(localized: "agent.subagent.toolUses"),
                    value: "\(toolUses)"
                )
            }
            if let durationMs = subagent.durationMs {
                detailRow(
                    icon: "clock",
                    label: String(localized: "agent.subagent.duration"),
                    value: formatDuration(ms: durationMs)
                )
            }
        }
        .padding(.leading, 32)
    }

    private func detailRow(icon: String, label: String, value: String) -> some View {
        HStack(alignment: .top, spacing: RFSpacing.xs) {
            Image(systemName: icon)
                .font(.caption)
                .foregroundStyle(RFColors.fallbackTextTertiary)
                .frame(width: 16)
            VStack(alignment: .leading, spacing: 1) {
                RFText(label, style: .caption, color: RFColors.fallbackTextTertiary)
                RFText(value, style: .caption, color: RFColors.fallbackTextSecondary)
            }
        }
    }

    private var isolationBadge: some View {
        HStack(spacing: 2) {
            Image(systemName: "tray.full")
                .font(.system(size: 9, weight: .semibold))
            RFText(
                String(localized: "agent.subagent.isolation.worktree"),
                style: .captionBold,
                color: RFColors.fallbackPrimary
            )
        }
        .foregroundStyle(RFColors.fallbackPrimary)
        .padding(.horizontal, RFSpacing.xs)
        .padding(.vertical, 2)
        .background(RFColors.fallbackPrimary.opacity(0.12))
        .clipShape(Capsule())
    }

    // MARK: - Helpers

    private var accessibilityLabel: String {
        let parts: [String] = [
            subagent.name,
            statusLabel(for: subagent.status),
            subagent.promptPreview
        ]
        return parts.filter { !$0.isEmpty }.joined(separator: ". ")
    }

    private func statusLabel(for status: SubagentStatus) -> String {
        switch status {
        case .spawned: return String(localized: "agent.subagent.status.spawned")
        case .inProgress: return String(localized: "agent.subagent.status.inProgress")
        case .completed: return String(localized: "agent.subagent.status.completed")
        case .failed: return String(localized: "agent.subagent.status.failed")
        }
    }

    private func statusColor(for status: SubagentStatus) -> Color {
        switch status {
        case .spawned: return RFColors.fallbackTextSecondary
        case .inProgress: return RFColors.fallbackPrimary
        case .completed: return RFColors.success
        case .failed: return RFColors.error
        }
    }

    private func formatDuration(ms: Int) -> String {
        if ms < 1_000 {
            return "\(ms)\(String(localized: "agent.subagent.duration.unit.ms"))"
        }
        let seconds = Double(ms) / 1_000.0
        if seconds < 60 {
            return String(format: "%.1f%@", seconds, String(localized: "agent.subagent.duration.unit.seconds"))
        }
        let minutes = Int(seconds) / 60
        let remaining = Int(seconds) % 60
        let minLabel = String(localized: "agent.subagent.duration.unit.minutes")
        let secLabel = String(localized: "agent.subagent.duration.unit.seconds")
        return "\(minutes)\(minLabel) \(remaining)\(secLabel)"
    }
}

// MARK: - Status Icon

/// Status'a gore animasyonlu / statik bir ikon. Spawned + inProgress
/// donen halka, completed checkmark, failed xmark.
struct SubagentStatusIcon: View {
    let status: SubagentStatus
    @State private var isAnimating = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Group {
            switch status {
            case .spawned, .inProgress:
                ZStack {
                    Circle()
                        .stroke(RFColors.fallbackPrimary.opacity(0.2), lineWidth: 2)
                    Circle()
                        .trim(from: 0, to: 0.7)
                        .stroke(
                            RFColors.brandGradient,
                            style: StrokeStyle(lineWidth: 2, lineCap: .round)
                        )
                        .rotationEffect(.degrees(isAnimating ? 360 : 0))
                        .animation(
                            reduceMotion
                                ? .default
                                : .linear(duration: 1).repeatForever(autoreverses: false),
                            value: isAnimating
                        )
                }
                .onAppear { isAnimating = !reduceMotion }
            case .completed:
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 22))
                    .foregroundStyle(RFColors.success)
            case .failed:
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 22))
                    .foregroundStyle(RFColors.error)
            }
        }
        .accessibilityHidden(true)
    }
}

// MARK: - Preview

#Preview("Subagent Tree — populated") {
    let viewModel = SubagentTreeViewModel(
        observeUseCase: ObserveSubagentsUseCase(repository: PreviewSubagentRepository())
    )
    viewModel.setSnapshot(SubagentTreePreviewData.sample)

    return NavigationStack {
        SubagentTreeView(sessionId: "preview-session", viewModel: viewModel)
    }
}

#Preview("Subagent Tree — empty (all sessions)") {
    let viewModel = SubagentTreeViewModel(
        observeUseCase: ObserveSubagentsUseCase(repository: PreviewSubagentRepository())
    )
    viewModel.setSnapshot([])

    return NavigationStack {
        SubagentTreeView(sessionId: nil, viewModel: viewModel)
    }
}

// MARK: - Preview Helpers

/// Preview / test icin no-op SubagentRepository.
private final class PreviewSubagentRepository: SubagentRepository, @unchecked Sendable {
    func observeSubagents(sessionId: String) async -> AsyncStream<[Subagent]> {
        AsyncStream { continuation in
            continuation.yield([])
            continuation.finish()
        }
    }
    func observeAllSubagents() async -> AsyncStream<[Subagent]> {
        AsyncStream { continuation in
            continuation.yield([])
            continuation.finish()
        }
    }
    func currentSubagents(sessionId: String) async -> [Subagent] { [] }
    func currentAllSubagents() async -> [Subagent] { [] }
    func apply(update: SubagentUpdate) async {}
    func clear(sessionId: String) async {}
}

/// Preview icin ornek subagent verisi: 1 kok + 2 child + 1 completed + 1 failed.
private enum SubagentTreePreviewData {
    static var sample: [Subagent] {
        let now = Date()
        let root = Subagent(
            id: "task-root",
            sessionId: "preview-session",
            parentTaskId: nil,
            name: "developer",
            description: "Implement feature X",
            promptPreview: "Add OutlineGroup-based subagent tree to AgentDetailView",
            subagentType: "developer",
            isolation: "worktree",
            status: .inProgress,
            summary: nil,
            totalTokens: nil,
            toolUses: nil,
            durationMs: nil,
            activity: "writing tests",
            spawnedAt: now.addingTimeInterval(-300),
            updatedAt: now.addingTimeInterval(-30),
            completedAt: nil
        )
        let child1 = Subagent(
            id: "task-child-1",
            sessionId: "preview-session",
            parentTaskId: "task-root",
            name: "tester",
            description: "Write unit tests",
            promptPreview: "Author Swift Testing tests for SubagentRepositoryImpl",
            subagentType: "tester",
            isolation: nil,
            status: .completed,
            summary: "All tests pass (12/12)",
            totalTokens: 8_421,
            toolUses: 3,
            durationMs: 18_300,
            activity: nil,
            spawnedAt: now.addingTimeInterval(-200),
            updatedAt: now.addingTimeInterval(-20),
            completedAt: now.addingTimeInterval(-20)
        )
        let child2 = Subagent(
            id: "task-child-2",
            sessionId: "preview-session",
            parentTaskId: "task-root",
            name: "reviewer",
            description: nil,
            promptPreview: "Review SubagentTreeView for HIG compliance",
            subagentType: nil,
            isolation: "worktree",
            status: .failed,
            summary: "Found 1 issue: missing accessibility label",
            totalTokens: 2_180,
            toolUses: 1,
            durationMs: 4_900,
            activity: nil,
            spawnedAt: now.addingTimeInterval(-100),
            updatedAt: now.addingTimeInterval(-5),
            completedAt: now.addingTimeInterval(-5)
        )
        let standalone = Subagent(
            id: "task-standalone",
            sessionId: "preview-session",
            parentTaskId: nil,
            name: "search",
            description: "Find similar PRs",
            promptPreview: "grep for OutlineGroup usage in codebase",
            subagentType: "general-purpose",
            isolation: nil,
            status: .completed,
            summary: "3 matches",
            totalTokens: 512,
            toolUses: 1,
            durationMs: 800,
            activity: nil,
            spawnedAt: now.addingTimeInterval(-60),
            updatedAt: now.addingTimeInterval(-50),
            completedAt: now.addingTimeInterval(-50)
        )
        return [root, child1, child2, standalone]
    }
}
