import Foundation

/// Uygulama ayarlarini yukleme use case'i.
struct LoadSettingsUseCase: Sendable {
    private let repository: SettingsRepositoryProtocol

    init(repository: SettingsRepositoryProtocol) {
        self.repository = repository
    }

    /// Mevcut ayarlari yukler.
    /// - Returns: Mevcut uygulama ayarlari.
    func execute() -> AppSettings {
        repository.loadSettings()
    }
}
