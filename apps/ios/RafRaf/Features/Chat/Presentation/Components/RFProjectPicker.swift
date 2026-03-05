import SwiftUI

/// Chat ekraninda proje secici menu.
/// Toolbar'da gosterilir, aktif projeyi degistirmeye yarar.
/// Agent-scoped projeleri agent'a gore gruplar.
struct RFProjectPicker: View {
    let activeProjectName: String?
    /// Aktif secimin agent ID'si — nil ise global proje veya genel sohbet.
    let activeAgentId: String?
    /// Agent'lara bagli projeler — agent bazinda gruplanir.
    let agentProjects: [AgentProject]
    /// Agent baglantisindan bagimsiz global projeler.
    let projects: [Project]
    /// (agentId, projectId, projectName) — nil secenegi genel sohbeti temsil eder.
    let onSelect: (String?, String?, String?) -> Void

    /// Toolbar'da gosterilecek etiket.
    /// Agent projesi seciliyse "agentId / projectName", yoksa sadece proje adi.
    private var displayLabel: String {
        if let agentId = activeAgentId, let projectName = activeProjectName {
            return "\(agentId) / \(projectName)"
        }
        return activeProjectName ?? String(localized: "chat.project.general")
    }

    private var agentGroups: [(agentId: String, projects: [AgentProject])] {
        let active = agentProjects.filter(\.isActive)
        let grouped = Dictionary(grouping: active, by: \.agentId)
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

            // Agent bazli proje gruplari — Section basligiyla agent adi gosterilir,
            // projeler dogrudan altinda listelenir (nested menu yok, ekstra tiklanma yok).
            if !agentGroups.isEmpty {
                ForEach(agentGroups, id: \.agentId) { group in
                    Section(group.agentId) {
                        ForEach(group.projects) { project in
                            Button {
                                onSelect(project.agentId, project.projectId, project.projectName)
                            } label: {
                                Label(project.projectName, systemImage: "folder")
                            }
                        }
                    }
                }
            }

            // Global projeler (agent'a bagli olmayan)
            if !projects.isEmpty {
                Divider()
                ForEach(projects) { project in
                    Button {
                        onSelect(nil, project.id, project.name)
                    } label: {
                        Label(project.name, systemImage: "folder")
                    }
                }
            }
        } label: {
            HStack(spacing: RFSpacing.xxs) {
                Image(systemName: activeProjectName != nil ? "folder.fill" : "bubble.left.and.bubble.right")
                    .font(.system(size: 12, weight: .medium))
                RFText(displayLabel, style: .captionBold)
                    .lineLimit(1)
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
            )
        ],
        projects: [
            Project(name: "SideProject", status: .active)
        ],
        onSelect: { _, _, _ in }
    )
    .padding()
}
