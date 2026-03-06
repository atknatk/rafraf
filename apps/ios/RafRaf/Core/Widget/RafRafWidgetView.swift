import SwiftUI

/// Widget view shared between widget extension and in-app preview.
struct RafRafWidgetView: View {
    let data: WidgetData

    var body: some View {
        ZStack {
            // Background gradient
            LinearGradient(
                colors: [Color(.systemBackground), Color(.secondarySystemBackground)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )

            VStack(alignment: .leading, spacing: 8) {
                // Header: app icon + agent status
                HStack {
                    Image(systemName: "brain.head.profile")
                        .font(.title2)
                        .foregroundStyle(statusColor)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(data.agentName)
                            .font(.headline)
                            .lineLimit(1)
                        Text(statusLabel)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    // Message count badge
                    if data.todayMessageCount > 0 {
                        Text("\(data.todayMessageCount)")
                            .font(.title3.bold())
                            .foregroundStyle(.primary)
                    }
                }

                // Pulse summary
                if let summary = data.pulseSummary {
                    Text(summary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                }

                Spacer()

                // Footer: last update
                Text(data.updatedAt, style: .relative)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            .padding(12)
        }
    }

    private var statusColor: Color {
        switch data.agentStatus {
        case "online": return .green
        case "busy": return .orange
        default: return .gray
        }
    }

    private var statusLabel: String {
        switch data.agentStatus {
        case "online": return String(localized: "widget.status.online")
        case "busy": return String(localized: "widget.status.busy")
        default: return String(localized: "widget.status.offline")
        }
    }
}

#Preview("Widget Preview") {
    RafRafWidgetView(data: WidgetData(
        agentName: "Developer Agent",
        agentStatus: "online",
        todayMessageCount: 42,
        pulseSummary: "Bugün 3 özellik tamamlandı. Kod tabanı stabil görünüyor.",
        updatedAt: Date()
    ))
    .frame(width: 169, height: 169)
    .clipShape(RoundedRectangle(cornerRadius: 20))
}
