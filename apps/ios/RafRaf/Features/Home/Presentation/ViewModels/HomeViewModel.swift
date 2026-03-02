import Foundation
import os

/// Ana sayfa ViewModel.
/// Home ekraninin durumunu ve islemlerini yonetir.
@Observable
@MainActor
final class HomeViewModel {
    // MARK: - State

    var isLoading: Bool = false
    var errorMessage: String?

    // MARK: - Private

    private let logger = AppLogger.logger(for: "Home")

    // MARK: - Init

    init() {
        logger.info("HomeViewModel baslatildi")
    }

    // MARK: - Actions

    /// Verileri yukler.
    func loadData() async {
        isLoading = true
        defer { isLoading = false }

        logger.info("Home verileri yukleniyor")

        // Placeholder - feature implementasyonunda doldurulacak
    }
}
