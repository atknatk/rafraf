import Foundation
import os

/// Proje detay ViewModel.
/// Tek projenin detay bilgisini yonetir.
@Observable
@MainActor
final class ProjectDetailViewModel {
    // MARK: - State

    var project: Project?
    var isLoading: Bool = false
    var errorMessage: String?

    // MARK: - Private

    private let getProjectDetailUseCase: GetProjectDetailUseCase
    private let projectId: String
    private let logger = AppLogger.logger(for: "ProjectDetail")

    // MARK: - Init

    init(
        getProjectDetailUseCase: GetProjectDetailUseCase,
        projectId: String
    ) {
        self.getProjectDetailUseCase = getProjectDetailUseCase
        self.projectId = projectId
        logger.info("ProjectDetailViewModel baslatildi - project: \(projectId)")
    }

    // MARK: - Actions

    /// Proje detayini yukler.
    func loadProject() async {
        guard !isLoading else { return }

        isLoading = true
        errorMessage = nil

        do {
            project = try await getProjectDetailUseCase.execute(projectId: projectId)
            logger.info("Proje detayi yuklendi: \(project?.name ?? "?")")
        } catch {
            errorMessage = String(localized: "project.error.detailFailed")
            logger.error("Proje detay yukleme hatasi: \(error.localizedDescription)")
        }

        isLoading = false
    }

    /// Hata mesajini temizler.
    func dismissError() {
        errorMessage = nil
    }
}
