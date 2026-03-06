import Foundation
import os

/// Proje olusturma ve duzenleme formu ViewModel.
/// nil projectId => yeni proje (POST), non-nil => duzenleme (PATCH).
@Observable
@MainActor
final class ProjectFormViewModel {
    // MARK: - Form Fields

    var name: String = ""
    var description: String = ""
    var repositoryURL: String = ""
    var localPath: String = ""
    /// Virgullerle ayrilmis teknoloji listesi (ornek: "Swift, Python").
    var techStackInput: String = ""

    // MARK: - State

    var isLoading: Bool = false
    var errorMessage: String? = nil
    var didSave: Bool = false

    // MARK: - Private

    private let repository: ProjectStatusRepositoryProtocol
    private let projectId: String?
    private let logger = AppLogger.logger(for: "ProjectFormViewModel")

    // MARK: - Init

    /// - Parameters:
    ///   - repository: Proje repository protokolu
    ///   - projectId: Duzenleme icin proje ID; nil ise yeni proje olusturulur
    ///   - existingProject: Duzenleme icin mevcut proje (form alanlarini doldurur)
    init(
        repository: ProjectStatusRepositoryProtocol,
        projectId: String? = nil,
        existingProject: Project? = nil
    ) {
        self.repository = repository
        self.projectId = projectId

        if let project = existingProject {
            self.name = project.name
            self.description = project.description ?? ""
            self.repositoryURL = project.repositoryURL ?? ""
            self.localPath = project.localPath ?? ""
            self.techStackInput = project.techStack.joined(separator: ", ")
        }
    }

    // MARK: - Computed

    var isEditMode: Bool { projectId != nil }

    var nameIsValid: Bool { !name.trimmingCharacters(in: .whitespaces).isEmpty }

    private var parsedTechStack: [String] {
        techStackInput
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    // MARK: - Actions

    /// Formu kaydeder: yeni proje ise POST, duzenleme ise PATCH.
    func save() async {
        guard nameIsValid else {
            errorMessage = String(localized: "project.form.error.nameRequired")
            return
        }

        isLoading = true
        errorMessage = nil

        do {
            if let projectId {
                _ = try await repository.updateProject(
                    projectId: projectId,
                    name: name.trimmingCharacters(in: .whitespaces),
                    description: description.isEmpty ? nil : description,
                    repositoryURL: repositoryURL.isEmpty ? nil : repositoryURL,
                    localPath: localPath.isEmpty ? nil : localPath,
                    techStack: parsedTechStack.isEmpty ? nil : parsedTechStack
                )
                logger.info("Proje guncellendi: \(projectId)")
            } else {
                _ = try await repository.createProject(
                    name: name.trimmingCharacters(in: .whitespaces),
                    description: description.isEmpty ? nil : description,
                    repositoryURL: repositoryURL.isEmpty ? nil : repositoryURL,
                    localPath: localPath.isEmpty ? nil : localPath,
                    techStack: parsedTechStack
                )
                logger.info("Yeni proje olusturuldu: \(self.name)")
            }
            didSave = true
        } catch {
            logger.error("Proje kaydedilemedi: \(error.localizedDescription)")
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    func dismissError() {
        errorMessage = nil
    }
}
