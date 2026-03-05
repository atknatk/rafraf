import Foundation
import os

/// Proje listesi ViewModel.
/// Proje listesinin durumunu ve islemlerini yonetir.
/// Filtreleme (status + agent), sayfalama ve pull-to-refresh destegi.
@Observable
@MainActor
final class ProjectListViewModel {
    // MARK: - State

    var projects: [Project] = []
    var agents: [Agent] = []
    var isLoading: Bool = false
    var isRefreshing: Bool = false
    var isLoadingMore: Bool = false
    var errorMessage: String?
    var selectedFilter: ProjectStatus?
    var selectedAgentId: String?
    var hasMorePages: Bool = false

    // MARK: - Private

    private let getProjectsUseCase: GetProjectsUseCase
    private let updateProjectStatusUseCase: UpdateProjectStatusUseCase
    private let getAgentsUseCase: GetAgentsUseCase
    private var currentPage: Int = 1
    private let pageSize: Int = 20
    private let logger = AppLogger.logger(for: "ProjectList")

    // MARK: - Init

    init(
        getProjectsUseCase: GetProjectsUseCase,
        updateProjectStatusUseCase: UpdateProjectStatusUseCase,
        getAgentsUseCase: GetAgentsUseCase
    ) {
        self.getProjectsUseCase = getProjectsUseCase
        self.updateProjectStatusUseCase = updateProjectStatusUseCase
        self.getAgentsUseCase = getAgentsUseCase
        logger.info("ProjectListViewModel baslatildi")
    }

    // MARK: - Actions

    /// Ilk yuklemede hem projeleri hem agent listesini getirir.
    func loadProjects() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil
        currentPage = 1
        async let projectsLoad: Void = _fetchProjects(reset: true)
        async let agentsLoad: Void = _loadAgentsIfNeeded()
        _ = await (projectsLoad, agentsLoad)
        isLoading = false
    }

    /// Pull-to-refresh.
    func refreshProjects() async {
        isRefreshing = true
        currentPage = 1
        await _fetchProjects(reset: true)
        isRefreshing = false
    }

    /// Listedeki son iteme gelindiginde cagrılır — sonraki sayfayi yukler.
    func loadMoreProjectsIfNeeded(currentItem project: Project) async {
        guard hasMorePages, !isLoadingMore else { return }
        guard let last = projects.last, last.id == project.id else { return }
        isLoadingMore = true
        currentPage += 1
        do {
            let result = try await getProjectsUseCase.execute(
                status: selectedFilter,
                agentId: selectedAgentId,
                page: currentPage,
                pageSize: pageSize
            )
            projects.append(contentsOf: result.projects)
            hasMorePages = result.hasMore
            logger.info("Ek projeler yuklendi: \(result.projects.count) proje, sayfa: \(self.currentPage)")
        } catch {
            currentPage -= 1
            logger.error("Ek proje yukleme hatasi: \(error.localizedDescription)")
        }
        isLoadingMore = false
    }

    /// Durum filtresini degistirir.
    func filterByStatus(_ status: ProjectStatus?) async {
        selectedFilter = status
        currentPage = 1
        isLoading = true
        await _fetchProjects(reset: true)
        isLoading = false
    }

    /// Agent filtresini degistirir.
    func filterByAgent(_ agentId: String?) async {
        selectedAgentId = agentId
        currentPage = 1
        isLoading = true
        await _fetchProjects(reset: true)
        isLoading = false
    }

    /// Proje durumunu gunceller.
    func updateStatus(projectId: String, status: ProjectStatus) async {
        do {
            let updated = try await updateProjectStatusUseCase.execute(projectId: projectId, status: status)
            guard let index = projects.firstIndex(where: { $0.id == projectId }) else { return }
            if let filter = selectedFilter, updated.status != filter {
                projects.remove(at: index)
            } else {
                projects[index] = updated
            }
            logger.info("Proje durumu guncellendi: \(projectId) -> \(status.rawValue)")
        } catch {
            errorMessage = String(localized: "project.error.updateFailed")
            logger.error("Proje durum guncelleme hatasi: \(error.localizedDescription)")
        }
    }

    func dismissError() {
        errorMessage = nil
    }

    /// Duplicate projeleri siler ve listeyi yeniler.
    func deduplicateProjects() async {
        do {
            let deleted = try await getProjectsUseCase.deduplicate()
            logger.info("Deduplicate: \(deleted) proje silindi")
            currentPage = 1
            await _fetchProjects(reset: true)
        } catch {
            errorMessage = String(localized: "project.error.deduplicateFailed")
            logger.error("Deduplicate hatasi: \(error.localizedDescription)")
        }
    }

    // MARK: - Private Helpers

    private func _fetchProjects(reset: Bool) async {
        do {
            let result = try await getProjectsUseCase.execute(
                status: selectedFilter,
                agentId: selectedAgentId,
                page: currentPage,
                pageSize: pageSize
            )
            if reset {
                projects = result.projects
            } else {
                projects.append(contentsOf: result.projects)
            }
            hasMorePages = result.hasMore
            logger.info("Projeler yuklendi: \(result.projects.count) proje, toplam: \(result.total)")
        } catch {
            errorMessage = String(localized: "project.error.loadFailed")
            logger.error("Proje yukleme hatasi: \(error.localizedDescription)")
        }
    }

    private func _loadAgentsIfNeeded() async {
        guard agents.isEmpty else { return }
        do {
            let result = try await getAgentsUseCase.execute(status: nil)
            agents = result.agents
        } catch {
            logger.error("Agent listesi yuklenemedi: \(error.localizedDescription)")
        }
    }
}
