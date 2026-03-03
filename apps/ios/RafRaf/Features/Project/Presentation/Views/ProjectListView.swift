import SwiftUI

/// Proje listesi ekrani.
/// Kullanicinin projelerini filtreleyip goruntuleyebildigi ana liste ekrani.
/// Pull-to-refresh, LazyVStack ile performansli scroll ve sayfalama destegi.
struct ProjectListView: View {
    @State private var viewModel: ProjectListViewModel

    init(viewModel: ProjectListViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                filterBar
                contentView
            }
            .navigationTitle(String(localized: "project.list.title"))
            .task {
                await viewModel.loadProjects()
            }
            .refreshable {
                await viewModel.refreshProjects()
            }
            .overlay {
                if let errorMessage = viewModel.errorMessage {
                    errorBanner(message: errorMessage)
                }
            }
        }
    }

    // MARK: - Filter Bar

    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: RFSpacing.xs) {
                filterChip(
                    title: String(localized: "project.filter.all"),
                    isSelected: viewModel.selectedFilter == nil
                ) {
                    Task { await viewModel.filterByStatus(nil) }
                }

                ForEach(ProjectStatus.allCases, id: \.self) { status in
                    filterChip(
                        title: filterTitle(for: status),
                        isSelected: viewModel.selectedFilter == status
                    ) {
                        Task { await viewModel.filterByStatus(status) }
                    }
                }
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
        }
        .background(RFColors.fallbackBackground)
    }

    private func filterChip(
        title: String,
        isSelected: Bool,
        action: @escaping () -> Void
    ) -> some View {
        RFButton(
            title,
            style: isSelected ? .primary : .outline,
            size: .small,
            action: action
        )
    }

    private func filterTitle(for status: ProjectStatus) -> String {
        switch status {
        case .active:
            return String(localized: "project.filter.active")
        case .pending:
            return String(localized: "project.filter.pending")
        case .completed:
            return String(localized: "project.filter.completed")
        case .archived:
            return String(localized: "project.filter.archived")
        }
    }

    // MARK: - Content

    @ViewBuilder
    private var contentView: some View {
        if viewModel.isLoading {
            Spacer()
            RFLoadingView(message: String(localized: "project.loading"))
            Spacer()
        } else if viewModel.projects.isEmpty {
            Spacer()
            RFEmptyStateView(
                systemImage: "folder",
                title: String(localized: "project.empty.title"),
                message: String(localized: "project.empty.message")
            )
            Spacer()
        } else {
            projectList
        }
    }

    private var projectList: some View {
        ScrollView {
            LazyVStack(spacing: RFSpacing.sm) {
                ForEach(viewModel.projects) { project in
                    NavigationLink(value: project.id) {
                        RFProjectCard(project: project) {
                            // onTap is handled by NavigationLink
                        }
                        .allowsHitTesting(false)
                    }
                    .buttonStyle(.plain)
                }

                if viewModel.hasMorePages {
                    RFButton(
                        String(localized: "project.loadMore"),
                        style: .ghost,
                        size: .small
                    ) {
                        Task { await viewModel.loadMoreProjects() }
                    }
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, RFSpacing.sm)
                }
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
        }
        .navigationDestination(for: String.self) { projectId in
            ProjectDetailView(
                viewModel: ProjectDetailViewModel(
                    getProjectDetailUseCase: GetProjectDetailUseCase(
                        repository: PreviewProjectRepository()
                    ),
                    projectId: projectId
                )
            )
        }
    }

    // MARK: - Error Banner

    private func errorBanner(message: String) -> some View {
        VStack {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(RFColors.error)
                RFText(message, style: .body, color: .white)
                Spacer()
                RFButton(
                    String(localized: "project.error.dismiss"),
                    style: .ghost,
                    size: .small
                ) {
                    viewModel.dismissError()
                }
            }
            .padding(RFSpacing.sm)
            .background(RFColors.error.opacity(0.9))
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .padding(.horizontal, RFSpacing.md)
            .padding(.top, RFSpacing.xs)

            Spacer()
        }
    }
}

#Preview {
    ProjectListView(
        viewModel: ProjectListViewModel(
            getProjectsUseCase: GetProjectsUseCase(
                repository: PreviewProjectRepository()
            )
        )
    )
}

/// Preview icin mock repository.
final class PreviewProjectRepository: ProjectStatusRepositoryProtocol, @unchecked Sendable {
    func getProjects(
        status: ProjectStatus?,
        page: Int,
        pageSize: Int
    ) async throws -> ProjectListResult {
        let allProjects = [
            Project(
                name: "RafRaf",
                description: "AI Project Supervisor",
                status: .active,
                techStack: ["Swift", "Python", "FastAPI"],
                lastActivityAt: Date().addingTimeInterval(-3600),
                lastActivitySummary: "PR #42 merged"
            ),
            Project(
                name: "WebApp Dashboard",
                description: "Admin panel",
                status: .active,
                techStack: ["Next.js", "TypeScript", "PostgreSQL"],
                lastActivityAt: Date().addingTimeInterval(-7200),
                lastActivitySummary: "Deploy tamamlandi"
            ),
            Project(
                name: "Mobile App",
                status: .pending,
                techStack: ["Kotlin", "Jetpack Compose"],
                lastActivitySummary: "Code review bekliyor"
            ),
            Project(
                name: "Legacy API",
                description: "Eski REST API",
                status: .completed,
                techStack: ["Node.js", "Express"]
            )
        ]

        let filtered: [Project]
        if let status {
            filtered = allProjects.filter { $0.status == status }
        } else {
            filtered = allProjects
        }

        return ProjectListResult(
            projects: filtered,
            total: filtered.count,
            page: page,
            pageSize: pageSize
        )
    }

    func getProject(id projectId: String) async throws -> Project {
        Project(
            id: projectId,
            name: "RafRaf",
            description: "AI-driven proje yonetim sistemi. Sesli ve metin tabanli arayuz ile projeleri yonetir.",
            status: .active,
            repositoryURL: "https://github.com/atknatk/rafraf",
            techStack: ["Swift", "Python", "FastAPI", "PostgreSQL"],
            lastActivityAt: Date().addingTimeInterval(-3600),
            lastActivitySummary: "PR #42 merged"
        )
    }
}
