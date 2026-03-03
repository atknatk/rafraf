import Foundation
import Testing
@testable import RafRaf

/// SettingsViewModel testleri.
@Suite("SettingsViewModel Tests")
struct SettingsViewModelTests {

    @Test("SettingsViewModel baslangic displayName dogru olmali")
    @MainActor
    func initialDisplayName() {
        let viewModel = SettingsViewModel()

        #expect(viewModel.displayName == "RafRaf User")
    }

    @Test("SettingsViewModel baslangic email dogru olmali")
    @MainActor
    func initialEmail() {
        let viewModel = SettingsViewModel()

        #expect(viewModel.email == "user@rafraf.app")
    }

    @Test("SettingsViewModel appVersion bos olmamali")
    @MainActor
    func appVersionNotEmpty() {
        let viewModel = SettingsViewModel()

        #expect(!viewModel.appVersion.isEmpty)
    }

    @Test("SettingsViewModel errorMessage baslangicta nil olmali")
    @MainActor
    func initialErrorMessageNil() {
        let viewModel = SettingsViewModel()

        #expect(viewModel.errorMessage == nil)
    }
}
