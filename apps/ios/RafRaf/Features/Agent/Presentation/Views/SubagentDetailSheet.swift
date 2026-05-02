import SwiftUI

/// Tek bir Subagent calismasinin tum detaylarini gosteren modal sheet.
///
/// `SubagentTreeView`'da bir satira dokunuldugunda bu sheet acilir. Identity
/// (task_id, name, type, isolation), durum, prompt onizleme (280 karaktere
/// kadar + "Show more"), zaman cizelgesi (spawned -> updated -> completed),
/// token + sure metrikleri ve ozeti listeler.
///
/// Doc 10 §8 — T3.1 Agent feature subagent UI test polish.
struct SubagentDetailSheet: View {
    let subagent: Subagent

    @State private var isPromptExpanded: Bool = false
    @Environment(\.dismiss) private var dismiss

    /// Test/preview disabled icin opsiyonel haptic kapatma flag'i.
    private let hapticsEnabled: Bool

    init(subagent: Subagent, hapticsEnabled: Bool = true) {
        self.subagent = subagent
        self.hapticsEnabled = hapticsEnabled
    }

    /// Prompt 280 karakterden uzunsa truncated gosterilir.
    private static let promptCollapseLimit = 280

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: RFSpacing.md) {
                    identitySection
                    statusSection
                    promptSection
                    timelineSection
                    metricsSection
                    if let summary = subagent.summary, !summary.isEmpty {
                        summarySection(summary: summary)
                    }
                }
                .padding(.horizontal, RFSpacing.md)
                .padding(.vertical, RFSpacing.sm)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(RFColors.fallbackBackground)
            .navigationTitle(String(localized: "agent.subagent.detail.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(RFColors.fallbackTextTertiary)
                            .accessibilityLabel(String(localized: "common.close"))
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }

    // MARK: - Identity Section

    private var identitySection: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                sectionHeader(
                    icon: "person.crop.square",
                    title: String(localized: "agent.subagent.detail.identity")
                )

                detailField(
                    label: String(localized: "agent.subagent.detail.name"),
                    value: subagent.name
                )

                detailField(
                    label: String(localized: "agent.subagent.detail.taskId"),
                    value: subagent.id,
                    monospaced: true
                )

                if let type = subagent.subagentType, !type.isEmpty {
                    detailField(
                        label: String(localized: "agent.subagent.detail.type"),
                        value: type
                    )
                }

                if let isolation = subagent.isolation, !isolation.isEmpty {
                    HStack(spacing: RFSpacing.xs) {
                        RFText(
                            String(localized: "agent.subagent.detail.isolation"),
                            style: .caption,
                            color: RFColors.fallbackTextSecondary
                        )
                        Spacer(minLength: 0)
                        isolationBadge(isolation: isolation)
                    }
                }
            }
        }
    }

    // MARK: - Status Section

    private var statusSection: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                sectionHeader(
                    icon: "waveform.path.ecg",
                    title: String(localized: "agent.subagent.detail.status")
                )

                HStack(spacing: RFSpacing.sm) {
                    SubagentStatusIcon(status: subagent.status)
                        .frame(width: 28, height: 28)
                    VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                        RFText(statusLabel, style: .bodyBold, color: statusColor)
                        if let activity = subagent.activity, !activity.isEmpty {
                            RFText(activity, style: .caption, color: RFColors.fallbackTextSecondary)
                        }
                    }
                    Spacer(minLength: 0)
                }
            }
        }
    }

    // MARK: - Prompt Section

    private var promptSection: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                sectionHeader(
                    icon: "text.alignleft",
                    title: String(localized: "agent.subagent.detail.prompt")
                )

                if subagent.promptPreview.isEmpty {
                    RFText(
                        String(localized: "agent.subagent.detail.prompt.empty"),
                        style: .caption,
                        color: RFColors.fallbackTextTertiary
                    )
                } else {
                    promptBody
                }
            }
        }
    }

    @ViewBuilder
    private var promptBody: some View {
        let prompt = subagent.promptPreview
        let isOverflow = prompt.count > Self.promptCollapseLimit

        let displayText: String = {
            if isOverflow && !isPromptExpanded {
                let endIndex = prompt.index(prompt.startIndex, offsetBy: Self.promptCollapseLimit)
                return String(prompt[..<endIndex]) + "…"
            }
            return prompt
        }()

        RFText(displayText, style: .body, color: RFColors.fallbackTextSecondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .textSelection(.enabled)

        if isOverflow {
            Button {
                if hapticsEnabled {
                    HapticManager.selection()
                }
                withAnimation(.easeInOut(duration: 0.2)) {
                    isPromptExpanded.toggle()
                }
            } label: {
                HStack(spacing: RFSpacing.xxs) {
                    Image(systemName: isPromptExpanded ? "chevron.up" : "chevron.down")
                        .font(.caption2)
                    RFText(
                        isPromptExpanded
                            ? String(localized: "agent.subagent.detail.prompt.showLess")
                            : String(localized: "agent.subagent.detail.prompt.showMore"),
                        style: .captionBold,
                        color: RFColors.fallbackPrimary
                    )
                }
            }
            .buttonStyle(.plain)
            .accessibilityHint(
                String(localized: "agent.subagent.detail.prompt.expand.hint")
            )
        }
    }

    // MARK: - Timeline Section

    private var timelineSection: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                sectionHeader(
                    icon: "clock.arrow.circlepath",
                    title: String(localized: "agent.subagent.detail.timeline")
                )

                timelineRow(
                    icon: "circle.fill",
                    color: RFColors.fallbackTextSecondary,
                    label: String(localized: "agent.subagent.detail.timeline.spawned"),
                    date: subagent.spawnedAt
                )

                if let updatedAt = subagent.updatedAt {
                    timelineRow(
                        icon: "arrow.triangle.2.circlepath",
                        color: RFColors.fallbackPrimary,
                        label: String(localized: "agent.subagent.detail.timeline.updated"),
                        date: updatedAt
                    )
                }

                if let completedAt = subagent.completedAt {
                    timelineRow(
                        icon: subagent.status == .failed ? "xmark.circle" : "checkmark.circle",
                        color: subagent.status == .failed ? RFColors.error : RFColors.success,
                        label: String(localized: "agent.subagent.detail.timeline.completed"),
                        date: completedAt
                    )
                }
            }
        }
    }

    private func timelineRow(icon: String, color: Color, label: String, date: Date) -> some View {
        HStack(spacing: RFSpacing.sm) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundStyle(color)
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 1) {
                RFText(label, style: .caption, color: RFColors.fallbackTextSecondary)
                RFText(formattedTimestamp(for: date), style: .body)
            }
            Spacer(minLength: 0)
        }
    }

    // MARK: - Metrics Section

    private var metricsSection: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                sectionHeader(
                    icon: "speedometer",
                    title: String(localized: "agent.subagent.detail.metrics")
                )

                HStack(spacing: RFSpacing.md) {
                    metricCard(
                        icon: "circle.hexagonpath",
                        label: String(localized: "agent.subagent.tokens"),
                        value: subagent.totalTokens.map(formattedTokens) ?? emDash
                    )
                    metricCard(
                        icon: "wrench.and.screwdriver",
                        label: String(localized: "agent.subagent.toolUses"),
                        value: subagent.toolUses.map { "\($0)" } ?? emDash
                    )
                    metricCard(
                        icon: "clock",
                        label: String(localized: "agent.subagent.duration"),
                        value: subagent.durationMs.map(formattedDuration) ?? emDash
                    )
                }
            }
        }
    }

    private func metricCard(icon: String, label: String, value: String) -> some View {
        VStack(spacing: RFSpacing.xxs) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundStyle(RFColors.fallbackPrimary)
            RFText(value, style: .headline)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            RFText(label, style: .caption, color: RFColors.fallbackTextSecondary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, RFSpacing.xs)
        .background(RFColors.fallbackSurface)
        .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.small))
    }

    // MARK: - Summary Section

    private func summarySection(summary: String) -> some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                sectionHeader(
                    icon: "doc.text",
                    title: String(localized: "agent.subagent.detail.summary")
                )
                RFText(summary, style: .body, color: RFColors.fallbackTextSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
        }
    }

    // MARK: - Helpers

    private let emDash = "—"

    private func sectionHeader(icon: String, title: String) -> some View {
        HStack(spacing: RFSpacing.xs) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(RFColors.fallbackPrimary)
            RFText(title, style: .headline)
            Spacer(minLength: 0)
        }
    }

    private func detailField(label: String, value: String, monospaced: Bool = false) -> some View {
        HStack(alignment: .top) {
            RFText(label, style: .caption, color: RFColors.fallbackTextSecondary)
                .frame(width: 80, alignment: .leading)
            if monospaced {
                Text(value)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(RFColors.fallbackTextPrimary)
                    .textSelection(.enabled)
            } else {
                RFText(value, style: .body)
                    .textSelection(.enabled)
            }
            Spacer(minLength: 0)
        }
    }

    private func isolationBadge(isolation: String) -> some View {
        HStack(spacing: 2) {
            Image(systemName: "tray.full")
                .font(.system(size: 10, weight: .semibold))
            RFText(
                isolation == "worktree"
                    ? String(localized: "agent.subagent.isolation.worktree")
                    : isolation,
                style: .captionBold,
                color: RFColors.fallbackPrimary
            )
        }
        .foregroundStyle(RFColors.fallbackPrimary)
        .padding(.horizontal, RFSpacing.xs)
        .padding(.vertical, 3)
        .background(RFColors.fallbackPrimary.opacity(0.12))
        .clipShape(Capsule())
    }

    private var statusLabel: String {
        switch subagent.status {
        case .spawned: return String(localized: "agent.subagent.status.spawned")
        case .inProgress: return String(localized: "agent.subagent.status.inProgress")
        case .completed: return String(localized: "agent.subagent.status.completed")
        case .failed: return String(localized: "agent.subagent.status.failed")
        }
    }

    private var statusColor: Color {
        switch subagent.status {
        case .spawned: return RFColors.fallbackTextSecondary
        case .inProgress: return RFColors.fallbackPrimary
        case .completed: return RFColors.success
        case .failed: return RFColors.error
        }
    }

    private func formattedTimestamp(for date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .medium
        return formatter.string(from: date)
    }

    private func formattedTokens(_ count: Int) -> String {
        if count >= 1_000 {
            let value = Double(count) / 1_000.0
            return String(format: "%.1fk", value)
        }
        return "\(count)"
    }

    private func formattedDuration(_ ms: Int) -> String {
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

    /// Test gorunurlugu icin pure helper'lari static olarak da expose ediyoruz.
    /// Boylece test, `init` yapmadan format dogrulugunu kontrol edebilir.
    nonisolated static func truncatePromptForDisplay(_ prompt: String, expanded: Bool) -> String {
        guard prompt.count > promptCollapseLimit else { return prompt }
        if expanded { return prompt }
        let endIndex = prompt.index(prompt.startIndex, offsetBy: promptCollapseLimit)
        return String(prompt[..<endIndex]) + "…"
    }

    nonisolated static func shouldShowExpandToggle(for prompt: String) -> Bool {
        prompt.count > promptCollapseLimit
    }
}

// MARK: - Preview

#Preview("Detail — completed") {
    SubagentDetailSheet(
        subagent: Subagent(
            id: "task-1",
            sessionId: "sess-1",
            parentTaskId: nil,
            name: "developer",
            description: "Implement subagent detail sheet",
            promptPreview: String(repeating: "Implement subagent detail sheet with multiple sections including identity, status, prompt preview with show more / less toggle, activity timeline, token + duration metrics and a summary block. ", count: 4),
            subagentType: "developer",
            isolation: "worktree",
            status: .completed,
            summary: "All sections rendered, 12 tests pass.",
            totalTokens: 12_800,
            toolUses: 7,
            durationMs: 32_500,
            activity: nil,
            spawnedAt: Date().addingTimeInterval(-300),
            updatedAt: Date().addingTimeInterval(-180),
            completedAt: Date().addingTimeInterval(-120)
        )
    )
}

#Preview("Detail — in progress") {
    SubagentDetailSheet(
        subagent: Subagent(
            id: "task-2",
            sessionId: "sess-1",
            parentTaskId: nil,
            name: "tester",
            description: nil,
            promptPreview: "Write Swift Testing tests for SubagentDetailSheet",
            subagentType: "tester",
            isolation: nil,
            status: .inProgress,
            summary: nil,
            totalTokens: nil,
            toolUses: nil,
            durationMs: nil,
            activity: "running tests",
            spawnedAt: Date().addingTimeInterval(-60),
            updatedAt: Date().addingTimeInterval(-10),
            completedAt: nil
        )
    )
}

#Preview("Detail — failed") {
    SubagentDetailSheet(
        subagent: Subagent(
            id: "task-3",
            sessionId: "sess-1",
            parentTaskId: nil,
            name: "reviewer",
            description: nil,
            promptPreview: "Review SubagentDetailSheet for HIG compliance",
            subagentType: nil,
            isolation: "worktree",
            status: .failed,
            summary: "Found 1 issue: missing accessibility label",
            totalTokens: 2_100,
            toolUses: 1,
            durationMs: 4_800,
            activity: nil,
            spawnedAt: Date().addingTimeInterval(-200),
            updatedAt: Date().addingTimeInterval(-30),
            completedAt: Date().addingTimeInterval(-30)
        )
    )
}
