import SwiftUI

/// Hizli komut tanimlari.
struct QuickCommand: Identifiable, Sendable {
    let id: String
    let trigger: String       // "/diff"
    let icon: String          // SF Symbol name
    let title: String         // Display title
    let description: String   // Short description
    let fullText: String      // What gets inserted into input
}

/// Tum hazir komutlar.
enum QuickCommands {
    static let all: [QuickCommand] = [
        QuickCommand(
            id: "diff",
            trigger: "/diff",
            icon: "doc.text.magnifyingglass",
            title: "/diff",
            description: String(localized: "commands.diff.desc"),
            fullText: String(localized: "commands.diff.text")
        ),
        QuickCommand(
            id: "status",
            trigger: "/status",
            icon: "info.circle",
            title: "/status",
            description: String(localized: "commands.status.desc"),
            fullText: String(localized: "commands.status.text")
        ),
        QuickCommand(
            id: "test",
            trigger: "/test",
            icon: "checkmark.seal",
            title: "/test",
            description: String(localized: "commands.test.desc"),
            fullText: String(localized: "commands.test.text")
        ),
        QuickCommand(
            id: "review",
            trigger: "/review",
            icon: "eye",
            title: "/review",
            description: String(localized: "commands.review.desc"),
            fullText: String(localized: "commands.review.text")
        ),
        QuickCommand(
            id: "commit",
            trigger: "/commit",
            icon: "arrow.triangle.branch",
            title: "/commit",
            description: String(localized: "commands.commit.desc"),
            fullText: String(localized: "commands.commit.text")
        ),
        QuickCommand(
            id: "deploy",
            trigger: "/deploy",
            icon: "airplane",
            title: "/deploy",
            description: String(localized: "commands.deploy.desc"),
            fullText: String(localized: "commands.deploy.text")
        ),
        QuickCommand(
            id: "help",
            trigger: "/help",
            icon: "questionmark.circle",
            title: "/help",
            description: String(localized: "commands.help.desc"),
            fullText: String(localized: "commands.help.text")
        ),
        QuickCommand(
            id: "optimize",
            trigger: "/optimize",
            icon: "bolt",
            title: "/optimize",
            description: String(localized: "commands.optimize.desc"),
            fullText: String(localized: "commands.optimize.text")
        ),
    ]

    /// Filtrele — query "" ise tum komutlar, "/" ile baslayan input icin eslesen komutlar.
    static func filtered(by query: String) -> [QuickCommand] {
        let lower = query.lowercased().trimmingCharacters(in: .whitespaces)
        if lower == "/" || lower.isEmpty { return all }
        return all.filter {
            $0.trigger.lowercased().hasPrefix(lower) ||
            $0.description.lowercased().contains(lower)
        }
    }
}

/// Hizli komut paleti popup gorunumu.
struct RFQuickCommandPalette: View {
    let commands: [QuickCommand]
    let onSelect: (QuickCommand) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(commands) { command in
                commandRow(command)
                if command.id != commands.last?.id {
                    Divider()
                        .padding(.leading, 44)
                }
            }
        }
        .background(RFColors.fallbackSurface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.15), radius: 8, x: 0, y: -4)
    }

    private func commandRow(_ command: QuickCommand) -> some View {
        Button {
            onSelect(command)
        } label: {
            HStack(spacing: RFSpacing.sm) {
                Image(systemName: command.icon)
                    .font(.system(size: 16))
                    .foregroundStyle(RFColors.fallbackPrimary)
                    .frame(width: 28, height: 28)
                    .background(RFColors.fallbackPrimary.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 6))

                VStack(alignment: .leading, spacing: 2) {
                    RFText(command.title, style: .bodyBold, color: RFColors.fallbackTextPrimary)
                    RFText(command.description, style: .caption, color: RFColors.fallbackTextSecondary)
                        .lineLimit(1)
                }

                Spacer()

                Image(systemName: "arrow.up.left")
                    .font(.system(size: 11))
                    .foregroundStyle(RFColors.fallbackTextTertiary)
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

#Preview {
    RFQuickCommandPalette(
        commands: QuickCommands.all,
        onSelect: { _ in }
    )
    .padding()
    .background(RFColors.fallbackBackground)
}
