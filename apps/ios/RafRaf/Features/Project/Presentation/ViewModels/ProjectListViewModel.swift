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
    private var currentPage: Int = 1
    private var totalCount: Int = 0
    private var isLoadingMore: Bool = false
    private let pageSize: Int = 20
    private let logger = AppLogger.logger(for: "ProjectList")

    // MARK: - Init

    init(getProjectsUseCase: GetProjectsUseCase) {
        self.getProjectsUseCase = getProjectsUseCase
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
            logger.info("Ek projeler yuklendi: \(result.projects.count) proje, sayfa: \(currentPage)")
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

    /// Hata mesajini temizler.
    func dismissError() {
        errorMessage = nil
    }
}
