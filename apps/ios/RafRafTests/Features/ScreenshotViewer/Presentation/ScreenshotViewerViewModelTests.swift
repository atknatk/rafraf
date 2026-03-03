import Foundation
import Testing
@testable import RafRaf

/// ScreenshotViewerViewModel testleri.
@Suite("ScreenshotViewerViewModel Tests")
struct ScreenshotViewerViewModelTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT(
        repository: MockScreenshotRepository = MockScreenshotRepository()
    ) -> (ScreenshotViewerViewModel, MockScreenshotRepository) {
        let vm = ScreenshotViewerViewModel(
            loadScreenshotUseCase: LoadScreenshotUseCase(repository: repository)
        )
        return (vm, repository)
    }

    // MARK: - Initial State

    @Test("Baslangic durumu dogru olmali")
    @MainActor
    func initialState() {
        let (vm, _) = makeSUT()

        #expect(vm.viewerState == .loading)
        #expect(vm.screenshot == nil)
        #expect(vm.isFullScreen == false)
        #expect(vm.currentScale == 1.0)
        #expect(vm.currentOffset == .zero)
        #expect(vm.errorMessage == nil)
    }

    // MARK: - loadFromURL

    @Test("loadFromURL gorsel durumunu loaded yapmalx")
    @MainActor
    func loadFromURL() {
        let (vm, _) = makeSUT()

        vm.loadFromURL(url: "https://example.com/img.png")

        #expect(vm.viewerState == .loaded)
        #expect(vm.screenshot != nil)
        #expect(vm.screenshot?.url == "https://example.com/img.png")
    }

    // MARK: - loadScreenshot

    @Test("Basarili screenshot yukleme loaded durumuna gecmeli")
    @MainActor
    func loadScreenshotSuccess() async {
        let expectedScreenshot = ScreenshotTestFactory.makeScreenshot(id: "sc-load")
        let repo = MockScreenshotRepository()
        repo.fetchScreenshotResult = .success(expectedScreenshot)
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadScreenshot(screenshotId: "sc-load")

        #expect(vm.viewerState == .loaded)
        #expect(vm.screenshot?.id == "sc-load")
        #expect(vm.errorMessage == nil)
    }

    @Test("Screenshot yukleme hatasi error durumuna gecmeli")
    @MainActor
    func loadScreenshotError() async {
        let repo = MockScreenshotRepository()
        repo.fetchScreenshotResult = .failure(ScreenshotRepositoryTestError.networkError)
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadScreenshot(screenshotId: "sc-error")

        if case .error = vm.viewerState {
            // Beklenen durum
        } else {
            Issue.record("Error durumu bekleniyordu, gelen: \(vm.viewerState)")
        }
        #expect(vm.errorMessage != nil)
    }

    // MARK: - Toggle Full Screen

    @Test("toggleFullScreen tam ekran modunu acmali")
    @MainActor
    func toggleFullScreenOpen() {
        let (vm, _) = makeSUT()

        vm.toggleFullScreen()

        #expect(vm.isFullScreen == true)
    }

    @Test("toggleFullScreen iki kez cagirilinca kapatmali")
    @MainActor
    func toggleFullScreenClose() {
        let (vm, _) = makeSUT()

        vm.toggleFullScreen()
        #expect(vm.isFullScreen == true)

        vm.toggleFullScreen()
        #expect(vm.isFullScreen == false)
    }

    @Test("toggleFullScreen kapatirken zoom sifirlanmali")
    @MainActor
    func toggleFullScreenResetsZoom() {
        let (vm, _) = makeSUT()

        vm.updateScale(3.0)
        vm.updateOffset(CGSize(width: 100, height: 50))
        vm.toggleFullScreen() // ac
        vm.toggleFullScreen() // kapat

        #expect(vm.currentScale == 1.0)
        #expect(vm.currentOffset == .zero)
    }

    // MARK: - dismissFullScreen

    @Test("dismissFullScreen tam ekrani kapatmali")
    @MainActor
    func dismissFullScreen() {
        let (vm, _) = makeSUT()

        vm.toggleFullScreen()
        #expect(vm.isFullScreen == true)

        vm.dismissFullScreen()
        #expect(vm.isFullScreen == false)
    }

    @Test("dismissFullScreen zoom sifirlamali")
    @MainActor
    func dismissFullScreenResetsZoom() {
        let (vm, _) = makeSUT()

        vm.updateScale(2.5)
        vm.toggleFullScreen()
        vm.dismissFullScreen()

        #expect(vm.currentScale == 1.0)
        #expect(vm.currentOffset == .zero)
    }

    // MARK: - Scale

    @Test("updateScale zoom seviyesini guncellemeli")
    @MainActor
    func updateScale() {
        let (vm, _) = makeSUT()

        vm.updateScale(2.5)

        #expect(vm.currentScale == 2.5)
    }

    @Test("updateScale minimum degerin altina inmemeli")
    @MainActor
    func updateScaleMinClamped() {
        let (vm, _) = makeSUT()

        vm.updateScale(0.5)

        #expect(vm.currentScale == vm.minScale)
    }

    @Test("updateScale maksimum degerin ustune cikmamali")
    @MainActor
    func updateScaleMaxClamped() {
        let (vm, _) = makeSUT()

        vm.updateScale(10.0)

        #expect(vm.currentScale == vm.maxScale)
    }

    // MARK: - Offset

    @Test("updateOffset pan degerini guncellemeli")
    @MainActor
    func updateOffset() {
        let (vm, _) = makeSUT()
        let newOffset = CGSize(width: 50, height: -30)

        vm.updateOffset(newOffset)

        #expect(vm.currentOffset == newOffset)
    }

    // MARK: - Reset Zoom

    @Test("resetZoom scale ve offset sifirlamali")
    @MainActor
    func resetZoom() {
        let (vm, _) = makeSUT()

        vm.updateScale(3.0)
        vm.updateOffset(CGSize(width: 100, height: 200))
        vm.resetZoom()

        #expect(vm.currentScale == 1.0)
        #expect(vm.currentOffset == .zero)
    }

    // MARK: - Double Tap Zoom

    @Test("doubleTapZoom 1x'ten 2.5x'e buyutmeli")
    @MainActor
    func doubleTapZoomIn() {
        let (vm, _) = makeSUT()

        vm.doubleTapZoom()

        #expect(vm.currentScale == 2.5)
    }

    @Test("doubleTapZoom zoomlu iken sifirlamali")
    @MainActor
    func doubleTapZoomOut() {
        let (vm, _) = makeSUT()

        vm.doubleTapZoom() // zoom in
        #expect(vm.currentScale == 2.5)

        vm.doubleTapZoom() // zoom out
        #expect(vm.currentScale == 1.0)
        #expect(vm.currentOffset == .zero)
    }

    // MARK: - Dismiss Error

    @Test("dismissError hata mesajini temizlemeli")
    @MainActor
    func dismissError() async {
        let repo = MockScreenshotRepository()
        repo.fetchScreenshotResult = .failure(ScreenshotRepositoryTestError.networkError)
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadScreenshot(screenshotId: "err")
        #expect(vm.errorMessage != nil)

        vm.dismissError()
        #expect(vm.errorMessage == nil)
    }

    // MARK: - Min/Max Scale

    @Test("minScale ve maxScale degerleri dogru olmali")
    @MainActor
    func scaleConstants() {
        let (vm, _) = makeSUT()

        #expect(vm.minScale == 1.0)
        #expect(vm.maxScale == 5.0)
    }
}
