import Factory
import SwiftUI

/// Chat ekraninda proje secici menu.
/// Toolbar'da gosterilir, aktif projeyi degistirmeye yarar.
struct RFProjectPicker: View {
    let activeProjectName: String?
    let projects: [Project]
    let onSelect: (String?, String?) -> Void

    var body: some View {
        Menu {
            // Genel sohbet secenegi
            Button {
                onSelect(nil, nil)
            } label: {
                Label(
                    String(localized: "chat.project.general"),
                    systemImage: "bubble.left.and.bubble.right"
                )
            }

            if !projects.isEmpty {
                Divider()

                ForEach(projects) { project in
                    Button {
                        onSelect(project.id, project.name)
                    } label: {
                        Label(project.name, systemImage: "folder")
                    }
                }
            }
        } label: {
            HStack(spacing: RFSpacing.xxs) {
                Image(systemName: activeProjectName != nil ? "folder.fill" : "bubble.left.and.bubble.right")
                    .font(.system(size: 12, weight: .medium))
                RFText(
                    activeProjectName ?? String(localized: "chat.project.general"),
                    style: .captionBold
                )
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
        projects: [
            Project(name: "RafRaf", status: .active),
            Project(name: "SideProject", status: .active)
        ],
        onSelect: { _, _ in }
    )
    .padding()
}
