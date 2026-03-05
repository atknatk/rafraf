import Factory
import SwiftUI

/// Proje listesi ekrani.
/// Kullanicinin projelerini filtreleyip goruntuleyebildigi ana liste ekrani.
/// Pull-to-refresh, status bazli section ve sayfalama destegi.
struct ProjectListView: View {
    @State private var viewModel: ProjectListViewModel
    @State private var showDeduplicateConfirm = false
    @State private var showCreateProject = false
    @Namespace private var filterNamespace
    private let projectRepository = Container.shared.projectRepository()

    init(viewModel: ProjectListViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if !viewModel.agents.isEmpty {
                    agentStatusBar
                }
                filterBar
                contentView
            }
            .navigationTitle(String(localized: "project.list.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showCreateProject = true
                    } label: {
                        Image(systemName: "plus")
                    }
                    .accessibilityLabel(String(localized: "project.action.create"))
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button(role: .destructive) {
                            showDeduplicateConfirm = true
                        } label: {
                            Label(
                                String(localized: "project.action.deduplicate"),
                                systemImage: "trash.slash"
                            )
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
            .sheet(isPresented: $showCreateProject, onDismiss: {
                Task { await viewModel.refreshProjects() }
            }) {
                ProjectFormView(
                    viewModel: ProjectFormViewModel(repository: projectRepository)
                )
            }
            .confirmationDialog(
                String(localized: "project.deduplicate.title"),
                isPresented: $showDeduplicateConfirm,
                titleVisibility: .visible
            ) {
                Button(String(localized: "project.deduplicate.confirm"), role: .destructive) {
                    Task { await viewModel.deduplicateProjects() }
                }
                Button(String(localized: "project.action.cancel"), role: .cancel) {}
            } message: {
                Text(String(localized: "project.deduplicate.message"))
            }
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

    // MARK: - Agent Status Bar

    private var agentStatusBar: some View {
        let online = viewModel.agents.filter { $0.status == .online }.count
        let busy = viewModel.agents.filter { $0.status == .busy }.count
        let offline = viewModel.agents.count - online - busy

        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: RFSpacing.md) {
                if online > 0 {
                    agentStatusPill(
                        count: online,
                        label: String(localized: "agent.status.online"),
                        color: RFColors.success
                    )
                }
                if busy > 0 {
                    agentStatusPill(
                        count: busy,
                        label: String(localized: "agent.status.busy"),
                        color: RFColors.warning
                    )
                }
                if offline > 0 {
                    agentStatusPill(
                        count: offline,
                        label: String(localized: "agent.status.offline"),
                        color: RFColors.fallbackTextTertiary
                    )
                }
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.xs)
        }
        .background(RFColors.fallbackSurface)
    }

    private func agentStatusPill(count: Int, label: String, color: Color) -> some View {
        HStack(spacing: RFSpacing.xxs) {
            Circle()
                .fill(color)
                .frame(width: 7, height: 7)
            RFText(
                "\(count) \(label)",
                style: .caption,
                color: RFColors.fallbackTextSecondary
            )
        }
    }

    // MARK: - Filter Bar

    private var filterBar: some View {
        VStack(spacing: 0) {
            // Status filtresi
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

            // Agent filtresi (birden fazla agent varsa goster)
            if !viewModel.agents.isEmpty {
                Divider()
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: RFSpacing.xs) {
                        filterChip(
                            title: String(localized: "project.filter.allAgents"),
                            isSelected: viewModel.selectedAgentId == nil,
                            namespace: "agentFilter"
                        ) {
                            Task { await viewModel.filterByAgent(nil) }
                        }
                        ForEach(viewModel.agents, id: \.hostId) { agent in
                            filterChip(
                                title: agent.hostId,
                                isSelected: viewModel.selectedAgentId == agent.hostId,
                                namespace: "agentFilter"
                            ) {
                                Task { await viewModel.filterByAgent(agent.hostId) }
                            }
                        }
                    }
                    .padding(.horizontal, RFSpacing.md)
                    .padding(.vertical, RFSpacing.sm)
                }
            }
        }
        .background(RFColors.fallbackBackground)
    }

    private func filterChip(
        title: String,
        isSelected: Bool,
        namespace: String = "activeFilter",
        action: @escaping () -> Void
    ) -> some View {
        Button {
            action()
        } label: {
            RFText(
                title,
                style: .captionBold,
                color: isSelected ? .white : RFColors.fallbackTextPrimary
            )
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.xs)
            .background {
                if isSelected {
                    RFColors.brandGradient
                        .matchedGeometryEffect(
                            id: namespace,
                            in: filterNamespace
                        )
                } else {
                    RFColors.fallbackSurface
                }
            }
            .clipShape(Capsule())
        }
        .buttonStyle(RFPressButtonStyle())
        .sensoryFeedback(.selection, trigger: isSelected)
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
            ProjectListSkeletonView()
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

    // Filtre yokken projeleri status'a gore grupla
    private var groupedProjects: [(status: ProjectStatus, projects: [Project])] {
        let order: [ProjectStatus] = [.active, .pending, .completed, .archived]
        return order.compactMap { status in
            let group = viewModel.projects.filter { $0.status == status }
            return group.isEmpty ? nil : (status: status, projects: group)
        }
    }

    private var projectList: some View {
        List {
            if viewModel.selectedFilter == nil {
                // Status bazli section gorunumu
                ForEach(groupedProjects, id: \.status) { group in
                    Section {
                        ForEach(group.projects) { project in
                            projectRow(project)
                        }
                    } header: {
                        HStack(spacing: RFSpacing.xxs) {
                            RFProjectStatusBadge(status: group.status)
                            Spacer()
                            RFText(
                                "\(group.projects.count)",
                                style: .captionBold,
                                color: RFColors.fallbackTextTertiary
                            )
                        }
                        .padding(.vertical, RFSpacing.xxs)
                    }
                }
            } else {
                ForEach(viewModel.projects) { project in
                    projectRow(project)
                }
            }
        }
        .listStyle(.plain)
        .navigationDestination(for: String.self) { projectId in
            ProjectDetailView(
                viewModel: ProjectDetailViewModel(
                    getProjectDetailUseCase: GetProjectDetailUseCase(
                        repository: projectRepository
                    ),
                    projectId: projectId
                )
            )
        }
    }

    private func projectRow(_ project: Project) -> some View {
        NavigationLink(value: project.id) {
            RFProjectCard(project: project) {}
                .allowsHitTesting(false)
        }
        .buttonStyle(.plain)
        .listRowInsets(EdgeInsets(
            top: RFSpacing.xs,
            leading: RFSpacing.md,
            bottom: RFSpacing.xs,
            trailing: RFSpacing.md
        ))
        .listRowBackground(Color.clear)
        .listRowSeparator(.hidden)
        .task {
            await viewModel.loadMoreProjectsIfNeeded(currentItem: project)
        }
        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
            if project.status == .active {
                Button(role: .destructive) {
                    Task { await viewModel.updateStatus(projectId: project.id, status: .archived) }
                } label: {
                    Label(String(localized: "project.action.archive"), systemImage: "archivebox")
                }
            } else if project.status != .archived {
                Button {
                    Task { await viewModel.updateStatus(projectId: project.id, status: .active) }
                } label: {
                    Label(String(localized: "project.action.activate"), systemImage: "checkmark.circle")
                }
                .tint(RFColors.success)
            }
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
            .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))
            .padding(.horizontal, RFSpacing.md)
            .padding(.top, RFSpacing.xs)

            Spacer()
        }
    }
}

#Preview {
    let repo = PreviewProjectRepository()
    let agentRepo = PreviewAgentRepository()
    ProjectListView(
        viewModel: ProjectListViewModel(
            getProjectsUseCase: GetProjectsUseCase(repository: repo),
            updateProjectStatusUseCase: UpdateProjectStatusUseCase(repository: repo),
            getAgentsUseCase: GetAgentsUseCase(repository: agentRepo)
        )
    )
}

/// Preview icin mock repository.
final class PreviewProjectRepository: ProjectStatusRepositoryProtocol, @unchecked Sendable {
    func getProjects(
        status: ProjectStatus?,
        agentId: String? = nil,
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

    func updateProjectStatus(projectId: String, status: ProjectStatus) async throws -> Project {
        Project(id: projectId, name: "RafRaf", status: status)
    }

    func deduplicateProjects() async throws -> Int { 0 }

    func createProject(
        name: String,
        description: String?,
        repositoryURL: String?,
        localPath: String?,
        techStack: [String]
    ) async throws -> String {
        UUID().uuidString
    }

    func updateProject(
        projectId: String,
        name: String?,
        description: String?,
        repositoryURL: String?,
        localPath: String?,
        techStack: [String]?
    ) async throws -> Project {
        Project(id: projectId, name: name ?? "RafRaf")
    }
}
