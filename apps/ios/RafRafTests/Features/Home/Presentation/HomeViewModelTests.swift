import Foundation
import Testing
@testable import RafRaf

/// HomeViewModel testleri.
@Suite("HomeViewModel Tests")
struct HomeViewModelTests {

    @Test("HomeViewModel baslangic durumu dogru olmali")
    @MainActor
    func initialState() {
        let viewModel = HomeViewModel()

        #expect(viewModel.isLoading == false)
        #expect(viewModel.errorMessage == nil)
    }

    @Test("loadData isLoading durumunu degistirmeli")
    @MainActor
    func loadDataUpdatesLoading() async {
        let viewModel = HomeViewModel()

        await viewModel.loadData()

        // loadData tamamlandiktan sonra isLoading false olmali
        #expect(viewModel.isLoading == false)
    }
}
