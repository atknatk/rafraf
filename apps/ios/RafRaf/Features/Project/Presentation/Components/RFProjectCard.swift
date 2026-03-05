import SwiftUI

/// Proje kart bileseni.
/// Proje listesinde her proje icin gosterilen ozet kart.
/// RFCard temel alinarak proje bilgilerini gosterir.
struct RFProjectCard: View {
    let project: Project
    let onTap: () -> Void

    var body: some View {
        RFCard(style: .interactive, onTap: onTap) {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                headerRow
                techStackRow
                activityRow
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Subviews

    private var headerRow: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                RFText(project.name, style: .title)

                if let description = project.description {
                    RFText(description, style: .caption)
                } else if let localPath = project.localPath {
                    HStack(spacing: RFSpacing.xxs) {
                        Image(systemName: "folder")
                            .font(.caption2)
                            .foregroundStyle(RFColors.fallbackTextSecondary)
                        RFText(shortPath(localPath), style: .caption, color: RFColors.fallbackTextSecondary)
                    }
                }
            }

            Spacer()

            RFProjectStatusBadge(status: project.status)
        }
    }

    private func shortPath(_ path: String) -> String {
        let components = path.split(separator: "/").map(String.init)
        guard components.count >= 2 else { return path }
        return "…/" + components.suffix(2).joined(separator: "/")
    }

    @ViewBuilder
    private var techStackRow: some View {
        if !project.techStack.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: RFSpacing.xxs) {
                    ForEach(project.techStack, id: \.self) { tech in
                        RFText(tech, style: .caption)
                            .padding(.horizontal, RFSpacing.xs)
                            .padding(.vertical, RFSpacing.xxs)
                            .background(RFColors.fallbackPrimary.opacity(0.08))
                            .clipShape(Capsule())
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var activityRow: some View {
        if let summary = project.lastActivitySummary {
            HStack(spacing: RFSpacing.xxs) {
                Image(systemName: "clock")
                    .font(.caption2)
                    .foregroundStyle(RFColors.fallbackTextTertiary)

                RFText(summary, style: .caption)

                if let activityDate = project.lastActivityAt {
                    Spacer()
                    RFText(
                        activityDate.formatted(.relative(presentation: .named)),
                        style: .caption
                    )
                }
            }
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFProjectCard(
            project: Project(
                name: "RafRaf",
                description: "AI Project Supervisor",
                status: .active,
                techStack: ["Swift", "Python", "FastAPI"],
                lastActivityAt: Date().addingTimeInterval(-3600),
                lastActivitySummary: "PR #42 merged"
            ),
            onTap: {}
        )

        RFProjectCard(
            project: Project(
                name: "WebApp",
                status: .pending,
                techStack: ["Next.js", "TypeScript"],
                lastActivitySummary: "Deploy bekliyor"
            ),
            onTap: {}
        )

        RFProjectCard(
            project: Project(
                name: "Legacy API",
                status: .completed,
                techStack: ["Node.js"]
            ),
            onTap: {}
        )
    }
    .padding()
}
