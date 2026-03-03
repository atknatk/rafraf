import Foundation
import Testing
@testable import RafRaf

/// SaveSettingsUseCase testleri.
@Suite("SaveSettingsUseCase Tests")
struct SaveSettingsUseCaseTests {

    @Test("execute ayarlari repository'ye kaydetmeli")
    func executeSaves() {
        let repository = MockSettingsRepository()
        let useCase = SaveSettingsUseCase(repository: repository)
        let settings = SettingsTestFactory.createCustomSettings()

        useCase.execute(settings: settings)

        #expect(repository.saveCallCount == 1)
        #expect(repository.lastSavedSettings == settings)
    }

    @Test("execute varsayilan ayarlari kaydetmeli")
    func executeSavesDefaults() {
        let repository = MockSettingsRepository()
        let useCase = SaveSettingsUseCase(repository: repository)

        useCase.execute(settings: .defaults)

        #expect(repository.saveCallCount == 1)
        #expect(repository.lastSavedSettings == AppSettings.defaults)
    }
}
