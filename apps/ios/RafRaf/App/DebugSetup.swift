#if DEBUG
import Factory
import Foundation
import os

/// DEBUG ortaminda Keychain'e API anahtarlarini enjekte eder.
/// Xcode scheme environment variables'dan okur (simulator'da calisir).
///
/// Kullanim:
/// 1. Xcode scheme > Run > Environment Variables'a `DEEPGRAM_API_KEY` ekleyin
/// 2. Degerini Deepgram dashboard'dan alin
/// 3. Uygulama baslatildiginda key otomatik olarak Keychain'e yazilir
enum DebugSetup {
    private static let logger = Logger(subsystem: "com.rafraf", category: "DebugSetup")

    /// Gelistirme anahtarlarini Keychain'e yazar.
    /// Sadece key henuz Keychain'de yoksa yazar.
    static func injectKeysIfNeeded() {
        let keychain = Container.shared.keychainHelper()
        injectDeepgramKey(keychain: keychain)
    }

    /// Deepgram API key — fiziksel cihaz icin buraya yazin.
    /// Simulator'da Xcode scheme environment variable kullanilir.
    private static let deepgramKeyOverride: String = ""

    private static func injectDeepgramKey(keychain: KeychainHelper) {
        // Zaten varsa atla
        if let existing = keychain.readString(for: RFSpeechRecognizer.deepgramAPIKeyKeychainKey),
           !existing.isEmpty {
            logger.debug("Deepgram API key zaten Keychain'de mevcut")
            return
        }

        // 1) Xcode scheme env var (simulator)
        // 2) Hardcoded override (fiziksel cihaz)
        let key = ProcessInfo.processInfo.environment["DEEPGRAM_API_KEY"]
            ?? (deepgramKeyOverride.isEmpty ? nil : deepgramKeyOverride)

        guard let apiKey = key, !apiKey.isEmpty else {
            logger.warning(
                "DEEPGRAM_API_KEY bulunamadi — scheme env var veya deepgramKeyOverride kullanin"
            )
            return
        }

        do {
            try keychain.saveString(apiKey, for: RFSpeechRecognizer.deepgramAPIKeyKeychainKey)
            logger.info("Deepgram API key Keychain'e enjekte edildi")
        } catch {
            logger.error("Deepgram API key kaydedilemedi: \(error)")
        }
    }
}
#endif
