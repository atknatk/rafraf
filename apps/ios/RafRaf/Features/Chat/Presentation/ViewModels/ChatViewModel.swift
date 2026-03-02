import Foundation
import os

/// Sohbet ViewModel.
/// Chat ekraninin durumunu ve islemlerini yonetir.
@Observable
@MainActor
final class ChatViewModel {
    // MARK: - State

    var isLoading: Bool = false
    var messageText: String = ""
    var errorMessage: String?

    // MARK: - Private

    private let logger = AppLogger.logger(for: "Chat")

    // MARK: - Init

    init() {
        logger.info("ChatViewModel baslatildi")
    }

    // MARK: - Actions

    /// Mesaj gonderir.
    func sendMessage() async {
        guard !messageText.isEmpty else { return }

        let text = messageText
        messageText = ""

        logger.info("Mesaj gonderiliyor: \(text.prefix(50))")

        // Placeholder - feature implementasyonunda WebSocket ile gonderilecek
    }
}
