import Foundation
import os

/// Proje listesi ViewModel.
/// Proje listesinin durumunu ve islemlerini yonetir.
/// Filtreleme, sayfalama ve pull-to-refresh destegi.
@Observable
@MainActor
final class ProjectListViewModel {
    // MARK: - State

    var projects: [Project] = []
    var isLoading: Bool = false
    var isRefreshing: Bool = false
    var errorMessage: String?
    var selectedFilter: ProjectStatus?
    var hasMorePages: Bool = false

    // MARK: - Private

    private let getProjectsUseCase: GetProjectsUseCase
    private let updateProjectStatusUseCase: UpdateProjectStatusUseCase
    private var currentPage: Int = 1
    private var totalCount: Int = 0
    private var isLoadingMore: Bool = false
    private let pageSize: Int = 100
    private let logger = AppLogger.logger(for: "ProjectList")

    // MARK: - Init

    init(getProjectsUseCase: GetProjectsUseCase, updateProjectStatusUseCase: UpdateProjectStatusUseCase) {
        self.getProjectsUseCase = getProjectsUseCase
        self.updateProjectStatusUseCase = updateProjectStatusUseCase
        logger.info("ProjectListViewModel baslatildi")
    }

    // MARK: - Actions

    /// Projeleri ilk sayfa olarak yukler.
    func loadProjects() async {
        guard !isLoading else { return }

        isLoading = true
        errorMessage = nil
        currentPage = 1

        do {
            let result = try await getProjectsUseCase.execute(
                status: selectedFilter,
                page: currentPage,
                pageSize: pageSize
            )
            projects = result.projects
            totalCount = result.total
            hasMorePages = result.hasMore
            logger.info("Projeler yuklendi: \(result.projects.count) proje, toplam: \(result.total)")
        } catch {
            errorMessage = String(localized: "project.error.loadFailed")
            logger.error("Proje yukleme hatasi: \(error.localizedDescription)")
        }

        isLoading = false
    }

    /// Pull-to-refresh ile projeleri yeniden yukler.
    func refreshProjects() async {
        isRefreshing = true
        currentPage = 1

        do {
            let result = try await getProjectsUseCase.execute(
                status: selectedFilter,
                page: currentPage,
                pageSize: pageSize
            )
            projects = result.projects
            totalCount = result.total
            hasMorePages = result.hasMore
            logger.info("Projeler yenilendi: \(result.projects.count) proje")
        } catch {
            errorMessage = String(localized: "project.error.refreshFailed")
            logger.error("Proje yenileme hatasi: \(error.localizedDescription)")
        }

        isRefreshing = false
    }

    /// Daha fazla proje yukler (sayfalama).
    func loadMoreProjects() async {
        guard hasMorePages, !isLoadingMore else { return }

        isLoadingMore = true
        currentPage += 1

        do {
            let result = try await getProjectsUseCase.execute(
                status: selectedFilter,
                page: currentPage,
                pageSize: pageSize
            )
            projects.append(contentsOf: result.projects)
            totalCount = result.total
            hasMorePages = result.hasMore
            logger.info("Ek projeler yuklendi: \(result.projects.count) proje, sayfa: \(self.currentPage)")
        } catch {
            currentPage -= 1
            logger.error("Ek proje yukleme hatasi: \(error.localizedDescription)")
        }

        isLoadingMore = false
    }

    /// Durum filtresini degistirir ve projeleri yeniden yukler.
    func filterByStatus(_ status: ProjectStatus?) async {
        selectedFilter = status
        await loadProjects()
    }

    /// Proje durumunu gunceller.
    /// Aktif filtre varsa ve guncellenen proje artik filtre kapsaminda degilse listeden cikarilir.
    func updateStatus(projectId: String, status: ProjectStatus) async {
        do {
            let updated = try await updateProjectStatusUseCase.execute(projectId: projectId, status: status)
            guard let index = projects.firstIndex(where: { $0.id == projectId }) else { return }
            // Filtre varsa ve proje artik filtre kapsaminda degilse listeden cikar
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

    /// Hata mesajini temizler.
    func dismissError() {
        errorMessage = nil
    }
}
