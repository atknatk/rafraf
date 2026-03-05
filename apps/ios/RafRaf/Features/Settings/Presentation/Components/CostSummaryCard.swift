import Charts
import Factory
import SwiftUI

/// API maliyet ozeti DTO.
private struct CostSummaryDTO: Codable, Sendable {
    let userId: String
    let period: String
    let since: String
    let costUsd: Double
    let tokenCount: Int
    let callCount: Int
}

/// Gunluk/Haftalik/Aylik API maliyetini gosteren kart.
struct CostSummaryCard: View {
    @State private var summary: CostSummaryDTO?
    @State private var selectedPeriod: Period = .daily
    @State private var isLoading = false

    private let networkClient = Container.shared.networkClient()

    enum Period: String, CaseIterable {
        case daily, weekly, monthly

        var label: String {
            switch self {
            case .daily: return String(localized: "cost.period.daily")
            case .weekly: return String(localized: "cost.period.weekly")
            case .monthly: return String(localized: "cost.period.monthly")
            }
        }
    }

    var body: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                HStack {
                    Image(systemName: "dollarsign.circle.fill")
                        .foregroundStyle(RFColors.fallbackPrimary)
                    RFText(String(localized: "cost.card.title"), style: .headline)
                    Spacer()
                    if isLoading {
                        ProgressView()
                            .scaleEffect(0.8)
                    }
                }

                Picker(String(localized: "cost.period.label"), selection: $selectedPeriod) {
                    ForEach(Period.allCases, id: \.self) { period in
                        Text(period.label).tag(period)
                    }
                }
                .pickerStyle(.segmented)

                if let summary {
                    summaryStats(summary)
                } else if !isLoading {
                    RFText(
                        String(localized: "cost.card.noData"),
                        style: .caption,
                        color: RFColors.fallbackTextSecondary
                    )
                }
            }
        }
        .task { await loadSummary() }
        .onChange(of: selectedPeriod) {
            Task { await loadSummary() }
        }
    }

    private func summaryStats(_ summary: CostSummaryDTO) -> some View {
        HStack(spacing: 0) {
            statCell(
                label: String(localized: "cost.stat.cost"),
                value: String(format: "$%.4f", summary.costUsd),
                icon: "dollarsign"
            )
            Divider().frame(height: 40)
            statCell(
                label: String(localized: "cost.stat.tokens"),
                value: formatNumber(summary.tokenCount),
                icon: "number"
            )
            Divider().frame(height: 40)
            statCell(
                label: String(localized: "cost.stat.calls"),
                value: "\(summary.callCount)",
                icon: "bolt"
            )
        }
        .padding(.top, RFSpacing.xxs)
    }

    private func statCell(label: String, value: String, icon: String) -> some View {
        VStack(spacing: RFSpacing.xxs) {
            Image(systemName: icon)
                .font(.caption)
                .foregroundStyle(RFColors.fallbackPrimary.opacity(0.7))
            RFText(value, style: .headline)
            RFText(label, style: .caption, color: RFColors.fallbackTextSecondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func loadSummary() async {
        isLoading = true
        defer { isLoading = false }
        summary = try? await networkClient.get(
            path: "/costs/summary",
            queryItems: [URLQueryItem(name: "period", value: selectedPeriod.rawValue)]
        )
    }

    private func formatNumber(_ n: Int) -> String {
        if n >= 1_000_000 { return String(format: "%.1fM", Double(n) / 1_000_000) }
        if n >= 1_000 { return String(format: "%.1fK", Double(n) / 1_000) }
        return "\(n)"
    }
}

#Preview {
    CostSummaryCard()
        .padding()
}
