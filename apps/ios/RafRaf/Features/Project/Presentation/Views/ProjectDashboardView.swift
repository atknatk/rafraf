import Charts
import Factory
import SwiftUI

/// Proje analitik dashboard gorünümü.
struct ProjectDashboardView: View {
    let projectId: String
    let projectName: String

    @State private var analytics: ProjectAnalytics?
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var selectedDays = 7
    private let networkClient = Container.shared.networkClient()

    private let dayOptions = [7, 14, 30]

    var body: some View {
        ScrollView {
            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 300)
            } else if let error = errorMessage {
                RFEmptyStateView(
                    systemImage: "exclamationmark.triangle",
                    title: String(localized: "dashboard.error.title"),
                    message: error
                )
            } else if let analytics {
                dashboardContent(analytics)
            }
        }
        .navigationTitle(String(localized: "dashboard.title"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Picker(String(localized: "dashboard.period"), selection: $selectedDays) {
                    ForEach(dayOptions, id: \.self) { day in
                        Text(dayLabel(day))
                            .tag(day)
                    }
                }
                .pickerStyle(.menu)
            }
        }
        .task { await loadAnalytics() }
        .onChange(of: selectedDays) { _, _ in Task { await loadAnalytics() } }
    }

    @ViewBuilder
    private func dashboardContent(_ a: ProjectAnalytics) -> some View {
        VStack(spacing: RFSpacing.md) {
            statsGrid(a)

            if !a.dailyActivity.isEmpty {
                activityChart(a.dailyActivity)
            }

            if !a.modelDistribution.isEmpty {
                modelDistributionCard(a.modelDistribution)
            }

            widgetPreviewSection(a)
        }
        .padding(RFSpacing.md)
    }

    @ViewBuilder
    private func statsGrid(_ a: ProjectAnalytics) -> some View {
        LazyVGrid(
            columns: [GridItem(.flexible()), GridItem(.flexible())],
            spacing: RFSpacing.sm
        ) {
            StatCard(
                title: String(localized: "dashboard.stat.messages"),
                value: "\(a.userMessages + a.assistantMessages)",
                subtitle: "\(a.userMessages) kullanici, \(a.assistantMessages) AI",
                icon: "message",
                color: .blue
            )
            StatCard(
                title: String(localized: "dashboard.stat.tokens"),
                value: formatNumber(a.totalTokens),
                subtitle: "Ort. \(a.avgTokensPerResponse) / yanit",
                icon: "bolt.fill",
                color: .orange
            )
            StatCard(
                title: String(localized: "dashboard.stat.cost"),
                value: "$\(String(format: "%.4f", a.totalCostUSD))",
                subtitle: "Ort. $\(String(format: "%.5f", a.avgCostPerMessageUSD)) / mesaj",
                icon: "dollarsign.circle",
                color: .green
            )
            StatCard(
                title: String(localized: "dashboard.stat.period"),
                value: "\(a.periodDays)",
                subtitle: String(localized: "dashboard.stat.period.days"),
                icon: "calendar",
                color: .purple
            )
        }
    }

    @ViewBuilder
    private func activityChart(_ activity: [DailyActivity]) -> some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                RFText(
                    String(localized: "dashboard.chart.title"),
                    style: .bodyBold,
                    color: RFColors.fallbackTextPrimary
                )
                Chart(activity) { day in
                    BarMark(
                        x: .value(String(localized: "dashboard.chart.date"), day.date, unit: .day),
                        y: .value(String(localized: "dashboard.chart.messages"), day.messageCount)
                    )
                    .foregroundStyle(RFColors.fallbackPrimary.gradient)
                    .cornerRadius(4)
                }
                .frame(height: 150)
                .chartXAxis {
                    AxisMarks(values: .stride(by: .day, count: max(1, activity.count / 5))) {
                        AxisValueLabel(format: .dateTime.month(.abbreviated).day())
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func modelDistributionCard(_ models: [String: Int]) -> some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                RFText(
                    String(localized: "dashboard.models.title"),
                    style: .bodyBold,
                    color: RFColors.fallbackTextPrimary
                )
                ForEach(models.sorted(by: { $0.value > $1.value }), id: \.key) { model, count in
                    HStack {
                        Circle()
                            .fill(modelColor(for: model))
                            .frame(width: 8, height: 8)
                        RFText(model, style: .body, color: RFColors.fallbackTextPrimary)
                            .lineLimit(1)
                        Spacer()
                        RFText("\(count)", style: .bodyBold, color: RFColors.fallbackTextSecondary)
                    }
                }
            }
        }
    }

    private func modelColor(for model: String) -> Color {
        let m = model.lowercased()
        if m.contains("haiku") { return .green }
        if m.contains("opus") { return .purple }
        if m.contains("sonnet") { return .blue }
        return .gray
    }

    private func formatNumber(_ n: Int) -> String {
        if n >= 1_000_000 { return String(format: "%.1fM", Double(n) / 1_000_000) }
        if n >= 1_000 { return String(format: "%.1fK", Double(n) / 1_000) }
        return "\(n)"
    }

    private func dayLabel(_ day: Int) -> String {
        switch day {
        case 7: return String(localized: "dashboard.days.7")
        case 14: return String(localized: "dashboard.days.14")
        case 30: return String(localized: "dashboard.days.30")
        default: return "\(day)"
        }
    }

    @ViewBuilder
    private func widgetPreviewSection(_ a: ProjectAnalytics) -> some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                RFText(
                    String(localized: "dashboard.widget.preview.title"),
                    style: .bodyBold,
                    color: RFColors.fallbackTextPrimary
                )
                RFText(
                    String(localized: "dashboard.widget.preview.subtitle"),
                    style: .caption,
                    color: RFColors.fallbackTextSecondary
                )

                HStack {
                    Spacer()
                    RafRafWidgetView(data: WidgetData(
                        agentName: projectName,
                        agentStatus: "online",
                        todayMessageCount: a.userMessages + a.assistantMessages,
                        pulseSummary: a.dailyActivity.isEmpty ? nil :
                            String(format: String(localized: "dashboard.widget.preview.pulse"),
                                   a.userMessages + a.assistantMessages,
                                   String(format: "%.4f", a.totalCostUSD)),
                        updatedAt: Date()
                    ))
                    .frame(width: 169, height: 169)
                    .clipShape(RoundedRectangle(cornerRadius: 20))
                    .shadow(color: .black.opacity(0.1), radius: 8, x: 0, y: 4)
                    Spacer()
                }
            }
        }
    }

    private func loadAnalytics() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let dto: ProjectAnalyticsDTO = try await networkClient.get(
                path: "/analytics/project",
                queryItems: [
                    URLQueryItem(name: "project_id", value: projectId),
                    URLQueryItem(name: "days", value: "\(selectedDays)"),
                ]
            )
            let mapped = ProjectAnalyticsMapper.toDomain(from: dto)
            analytics = mapped
            // Update widget data with fresh analytics
            await WidgetDataService.shared.update(
                agentName: projectName,
                agentStatus: "online",
                todayMessageCount: mapped.userMessages + mapped.assistantMessages,
                pulseSummary: mapped.dailyActivity.isEmpty ? nil :
                    "\(mapped.userMessages + mapped.assistantMessages) mesaj · $\(String(format: "%.4f", mapped.totalCostUSD))"
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// Kucuk istatistik karti.
private struct StatCard: View {
    let title: String
    let value: String
    let subtitle: String
    let icon: String
    let color: Color

    var body: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.xs) {
                HStack {
                    Image(systemName: icon)
                        .font(.system(size: 14))
                        .foregroundStyle(color)
                    Spacer()
                }
                RFText(value, style: .title, color: RFColors.fallbackTextPrimary)
                RFText(title, style: .captionBold, color: RFColors.fallbackTextSecondary)
                RFText(subtitle, style: .caption, color: RFColors.fallbackTextTertiary)
                    .lineLimit(2)
            }
        }
    }
}

#Preview {
    NavigationStack {
        ProjectDashboardView(
            projectId: "test-project-id",
            projectName: "Test Project"
        )
    }
}
