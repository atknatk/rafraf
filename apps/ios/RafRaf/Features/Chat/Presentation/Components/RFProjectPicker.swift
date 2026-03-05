import SwiftUI

/// Chat ekraninda proje secici menu.
/// Toolbar'da gosterilir, aktif projeyi degistirmeye yarar.
/// Iki kademe: once agent secilir (nested menu), sonra o agent'in aktif projeleri listelenir.
struct RFProjectPicker: View {
    let activeProjectName: String?
    /// Aktif secimin agent ID'si — nil ise genel sohbet.
    let activeAgentId: String?
    /// Agent'lara bagli projeler — aktif olanlar agent bazinda gruplanir.
    let agentProjects: [AgentProject]
    /// (agentId, projectId, projectName) — nil secenegi genel sohbeti temsil eder.
    let onSelect: (String?, String?, String?) -> Void

    /// Toolbar etiketi: "agent / proje" veya "Genel".
    private var displayLabel: String {
        if let agentId = activeAgentId, let projectName = activeProjectName {
            // Agent adini kisalt: "macbook-pro.local" → "macbook-pro"
            let shortAgent = agentId.components(separatedBy: ".").first ?? agentId
            return "\(shortAgent) / \(projectName)"
        }
        return activeProjectName ?? String(localized: "chat.project.general")
    }

    /// Aktif projeler, agent bazinda gruplanmis.
    private var agentGroups: [(agentId: String, projects: [AgentProject])] {
        let grouped = Dictionary(grouping: agentProjects.filter(\.isActive), by: \.agentId)
        return grouped.map { (agentId: $0.key, projects: $0.value) }
            .sorted { $0.agentId < $1.agentId }
    }

    var body: some View {
        Menu {
            // Genel sohbet
            Button {
                onSelect(nil, nil, nil)
            } label: {
                Label(
                    String(localized: "chat.project.general"),
                    systemImage: "bubble.left.and.bubble.right"
                )
            }

            // Her agent icin nested menu — Adim 1: agent sec, Adim 2: proje sec
            if !agentGroups.isEmpty {
                Divider()
                ForEach(agentGroups, id: \.agentId) { group in
                    Menu {
                        ForEach(group.projects) { project in
                            Button {
                                onSelect(project.agentId, project.projectId, project.projectName)
                            } label: {
                                let isActive = project.agentId == activeAgentId
                                    && project.projectName == activeProjectName
                                Label(
                                    project.projectName,
                                    systemImage: isActive ? "folder.fill" : "folder"
                                )
                            }
                        }
                    } label: {
                        Label(group.agentId, systemImage: "desktopcomputer")
                    }
                }
            }
        } label: {
            HStack(spacing: RFSpacing.xxs) {
                Image(systemName: activeProjectName != nil ? "folder.fill" : "bubble.left.and.bubble.right")
                    .font(.system(size: 12, weight: .medium))
                RFText(displayLabel, style: .captionBold)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Image(systemName: "chevron.down")
                    .font(.system(size: 10, weight: .semibold))
            }
            .foregroundStyle(RFColors.fallbackTextPrimary)
            .padding(.horizontal, RFSpacing.sm)
            .padding(.vertical, RFSpacing.xxs)
            .background(
                RoundedRectangle(cornerRadius: RFCornerRadius.small)
                    .fill(RFColors.fallbackSurface)
            )
        }
    }
}

#Preview {
    RFProjectPicker(
        activeProjectName: "RafRaf",
        activeAgentId: "macbook-pro",
        agentProjects: [
            AgentProject(
                agentId: "macbook-pro",
                projectId: "proj-1",
                projectName: "RafRaf",
                isActive: true,
                repositoryUrl: nil,
                localPath: nil,
                techStack: ["Swift"]
            ),
            AgentProject(
                agentId: "macbook-pro",
                projectId: "proj-2",
                projectName: "WebApp",
                isActive: true,
                repositoryUrl: nil,
                localPath: nil,
                techStack: ["TypeScript"]
            )
        ],
        onSelect: { _, _, _ in }
    )
    .padding()
}
