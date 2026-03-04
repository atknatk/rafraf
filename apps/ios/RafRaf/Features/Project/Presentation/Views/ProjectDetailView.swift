import SwiftUI

/// Proje detay ekrani.
/// Secilen projenin tum bilgilerini gosteren detay gorunumu.
struct ProjectDetailView: View {
    @State private var viewModel: ProjectDetailViewModel

    init(viewModel: ProjectDetailViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        Group {
            if viewModel.isLoading {
                RFLoadingView(message: String(localized: "project.detail.loading"))
            } else if let project = viewModel.project {
                projectContent(project)
            } else if let errorMessage = viewModel.errorMessage {
                RFErrorView(
                    message: errorMessage,
                    retryAction: {
                        Task { await viewModel.loadProject() }
                    }
                )
            }
        }
        .navigationTitle(viewModel.project?.name ?? String(localized: "project.detail.title"))
        .navigationBarTitleDisplayMode(.large)
        .task {
            await viewModel.loadProject()
        }
    }

    // MARK: - Project Content

    private func projectContent(_ project: Project) -> some View {
        ScrollView {
            VStack(spacing: RFSpacing.md) {
                statusSection(project)
                descriptionSection(project)
                techStackSection(project)
                activitySection(project)
                detailsSection(project)
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
        }
    }

    // MARK: - Sections

    private func statusSection(_ project: Project) -> some View {
        RFCard(style: .elevated) {
            HStack {
                VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                    RFText(String(localized: "project.detail.status"), style: .caption)
                    RFProjectStatusBadge(status: project.status)
                }

                Spacer()

                if let activityDate = project.lastActivityAt {
                    VStack(alignment: .trailing, spacing: RFSpacing.xxs) {
                        RFText(
                            String(localized: "project.detail.lastActivity"),
                            style: .caption
                        )
                        RFText(
                            activityDate.formatted(.relative(presentation: .named)),
                            style: .bodyBold
                        )
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func descriptionSection(_ project: Project) -> some View {
        if let description = project.description {
            RFCard {
                VStack(alignment: .leading, spacing: RFSpacing.xs) {
                    RFText(
                        String(localized: "project.detail.description"),
                        style: .subtitle
                    )
                    RFText(description, style: .body)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    @ViewBuilder
    private func techStackSection(_ project: Project) -> some View {
        if !project.techStack.isEmpty {
            RFCard {
                VStack(alignment: .leading, spacing: RFSpacing.xs) {
                    RFText(
                        String(localized: "project.detail.techStack"),
                        style: .subtitle
                    )

                    FlowLayout(spacing: RFSpacing.xxs) {
                        ForEach(project.techStack, id: \.self) { tech in
                            RFText(tech, style: .captionBold, color: RFColors.fallbackPrimary)
                                .padding(.horizontal, RFSpacing.sm)
                                .padding(.vertical, RFSpacing.xxs)
                                .background(
                                    RFColors.fallbackPrimary.opacity(0.10)
                                )
                                .clipShape(Capsule())
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    @ViewBuilder
    private func activitySection(_ project: Project) -> some View {
        if let summary = project.lastActivitySummary {
            RFCard {
                VStack(alignment: .leading, spacing: RFSpacing.xs) {
                    RFText(
                        String(localized: "project.detail.recentActivity"),
                        style: .subtitle
                    )

                    HStack(spacing: RFSpacing.xs) {
                        Image(systemName: "clock")
                            .foregroundStyle(RFColors.fallbackTextSecondary)
                        RFText(summary, style: .body)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    @ViewBuilder
    private func detailsSection(_ project: Project) -> some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.xs) {
                RFText(
                    String(localized: "project.detail.info"),
                    style: .subtitle
                )

                if let repoURL = project.repositoryURL {
                    detailRow(
                        icon: "link",
                        title: String(localized: "project.detail.repository"),
                        value: repoURL
                    )
                }

                detailRow(
                    icon: "calendar",
                    title: String(localized: "project.detail.createdAt"),
                    value: project.createdAt.formatted(date: .abbreviated, time: .omitted)
                )

                detailRow(
                    icon: "arrow.triangle.2.circlepath",
                    title: String(localized: "project.detail.updatedAt"),
                    value: project.updatedAt.formatted(date: .abbreviated, time: .shortened)
                )
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func detailRow(icon: String, title: String, value: String) -> some View {
        HStack(spacing: RFSpacing.xs) {
            Image(systemName: icon)
                .font(.caption)
                .foregroundStyle(RFColors.fallbackTextSecondary)
                .frame(width: 20)

            RFText(title, style: .caption)

            Spacer()

            RFText(value, style: .caption)
        }
    }
}

// MARK: - FlowLayout

/// Yatay akis duzeni - technoloji etiketleri icin.
/// Satirlara otomatik olarak tasma yapar.
struct FlowLayout: Layout {
    let spacing: CGFloat

    init(spacing: CGFloat = 8) {
        self.spacing = spacing
    }

    func sizeThatFits(
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) -> CGSize {
        let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        return layout(sizes: sizes, containerWidth: proposal.width ?? .infinity).size
    }

    func placeSubviews(
        in bounds: CGRect,
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) {
        let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        let offsets = layout(sizes: sizes, containerWidth: bounds.width).offsets

        for (index, subview) in subviews.enumerated() {
            subview.place(
                at: CGPoint(
                    x: bounds.minX + offsets[index].x,
                    y: bounds.minY + offsets[index].y
                ),
                proposal: .unspecified
            )
        }
    }

    private func layout(
        sizes: [CGSize],
        containerWidth: CGFloat
    ) -> (offsets: [CGPoint], size: CGSize) {
        var offsets: [CGPoint] = []
        var currentX: CGFloat = 0
        var currentY: CGFloat = 0
        var lineHeight: CGFloat = 0
        var maxWidth: CGFloat = 0

        for size in sizes {
            if currentX + size.width > containerWidth, currentX > 0 {
                currentX = 0
                currentY += lineHeight + spacing
                lineHeight = 0
            }

            offsets.append(CGPoint(x: currentX, y: currentY))
            lineHeight = max(lineHeight, size.height)
            currentX += size.width + spacing
            maxWidth = max(maxWidth, currentX - spacing)
        }

        return (
            offsets: offsets,
            size: CGSize(width: maxWidth, height: currentY + lineHeight)
        )
    }
}

#Preview {
    NavigationStack {
        ProjectDetailView(
            viewModel: ProjectDetailViewModel(
                getProjectDetailUseCase: GetProjectDetailUseCase(
                    repository: PreviewProjectRepository()
                ),
                projectId: "preview-id"
            )
        )
    }
}
