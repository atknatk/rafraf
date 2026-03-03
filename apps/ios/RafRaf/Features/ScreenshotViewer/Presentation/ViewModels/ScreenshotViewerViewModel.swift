import Foundation
import os

/// Screenshot viewer ViewModel.
/// Gorsel yuklemesini, zoom ve pan durumlarini yonetir.
@Observable
@MainActor
final class ScreenshotViewerViewModel {
    // MARK: - State

    var viewerState: ScreenshotViewerState = .loading
    var screenshot: Screenshot?
    var isFullScreen: Bool = false
    var currentScale: CGFloat = 1.0
    var currentOffset: CGSize = .zero
    var errorMessage: String?

    // MARK: - Constants

    let minScale: CGFloat = 1.0
    let maxScale: CGFloat = 5.0

    // MARK: - Private

    private let loadScreenshotUseCase: LoadScreenshotUseCase
    private let logger = AppLogger.logger(for: "ScreenshotViewer")

    // MARK: - Init

    init(loadScreenshotUseCase: LoadScreenshotUseCase) {
        self.loadScreenshotUseCase = loadScreenshotUseCase
        logger.info("ScreenshotViewerViewModel baslatildi")
    }

    // MARK: - Actions

    /// Screenshot'i URL'den yukler.
    /// - Parameter url: Screenshot URL'si.
    func loadFromURL(url: String) {
        let screenshotModel = Screenshot(url: url)
        self.screenshot = screenshotModel
        viewerState = .loaded
        logger.info("Screenshot URL'den yuklendi")
    }

    /// Screenshot'i ID ile yukler.
    /// - Parameter screenshotId: Screenshot benzersiz kimligi.
    func loadScreenshot(screenshotId: String) async {
        viewerState = .loading
        errorMessage = nil

        do {
            let result = try await loadScreenshotUseCase.execute(
                screenshotId: screenshotId
            )
            screenshot = result
            viewerState = .loaded
            logger.info("Screenshot yuklendi: \(screenshotId)")
        } catch {
            let message = String(localized: "screenshotViewer.error.loadFailed")
            viewerState = .error(message)
            errorMessage = message
            logger.error("Screenshot yukleme hatasi: \(error.localizedDescription)")
        }
    }

    /// Tam ekran modunu acar veya kapatir.
    func toggleFullScreen() {
        isFullScreen.toggle()
        if !isFullScreen {
            resetZoom()
        }
        logger.info("Tam ekran modu: \(self.isFullScreen)")
    }

    /// Tam ekran modunu kapatir.
    func dismissFullScreen() {
        isFullScreen = false
        resetZoom()
    }

    /// Zoom seviyesini gunceller.
    /// - Parameter scale: Yeni zoom orani.
    func updateScale(_ scale: CGFloat) {
        currentScale = min(max(scale, minScale), maxScale)
    }

    /// Pan ofsetini gunceller.
    /// - Parameter offset: Yeni offset degeri.
    func updateOffset(_ offset: CGSize) {
        currentOffset = offset
    }

    /// Zoom ve pan'i sifirlar.
    func resetZoom() {
        currentScale = 1.0
        currentOffset = .zero
    }

    /// Cift tikla ile zoom yapar.
    func doubleTapZoom() {
        if currentScale > minScale {
            resetZoom()
        } else {
            currentScale = 2.5
        }
    }

    /// Hata mesajini temizler.
    func dismissError() {
        errorMessage = nil
    }

    /// Yeniden yukleme yapar.
    func retry() async {
        guard let currentScreenshot = screenshot else { return }
        await loadScreenshot(screenshotId: currentScreenshot.id)
    }
}
