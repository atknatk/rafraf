import Foundation
import Testing
@testable import RafRaf

/// LoadSettingsUseCase testleri.
@Suite("LoadSettingsUseCase Tests")
struct LoadSettingsUseCaseTests {

    @Test("execute varsayilan ayarlari donmeli")
    func executeReturnsDefaults() {
        let repository = MockSettingsRepository()
        let useCase = LoadSettingsUseCase(repository: repository)

        let settings = useCase.execute()

        #expect(settings == AppSettings.defaults)
        #expect(repository.loadCallCount == 1)
    }

    @Test("execute ozel ayarlari donmeli")
    func executeReturnsCustom() {
        let repository = MockSettingsRepository()
        let customSettings = SettingsTestFactory.createCustomSettings()
        repository.storedSettings = customSettings
        let useCase = LoadSettingsUseCase(repository: repository)

        let settings = useCase.execute()

        #expect(settings == customSettings)
        #expect(settings.ttsSpeed == 1.5)
        #expect(settings.appearance == .dark)
    }
}
