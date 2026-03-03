import Foundation

/// Uygulama ayarlarini kaydetme use case'i.
struct SaveSettingsUseCase: Sendable {
    private let repository: SettingsRepositoryProtocol

    init(repository: SettingsRepositoryProtocol) {
        self.repository = repository
    }

    /// Ayarlari kaydeder.
    /// - Parameter settings: Kaydedilecek ayarlar.
    func execute(settings: AppSettings) {
        repository.saveSettings(settings)
    }
}
