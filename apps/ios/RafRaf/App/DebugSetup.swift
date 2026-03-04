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
    private static let deepgramKeyOverride: String = "7e910ca540b2c79b3cb3c493cd44ba5e30b0ba8c"

    private static func injectDeepgramKey(keychain: KeychainHelper) {
        // Zaten varsa atla
        if let existing = keychain.readString(for: RFSpeechRecognizer.deepgramAPIKeyKeychainKey),
           !existing.isEmpty {
            logger.debug("Deepgram API key zaten Keychain'de mevcut")
            return
        }

        // 1) Hardcoded override (fiziksel cihaz — en guvenilir)
        // 2) Xcode scheme env var (simulator)
        // 3) Repo root .env dosyasi
        let key: String?
        if !deepgramKeyOverride.isEmpty {
            key = deepgramKeyOverride
            logger.info("Deepgram API key override'dan alindi")
        } else if let envKey = ProcessInfo.processInfo.environment["DEEPGRAM_API_KEY"], !envKey.isEmpty {
            key = envKey
            logger.info("Deepgram API key scheme env var'dan alindi")
        } else if let dotEnvKey = readFromDotEnv("DEEPGRAM_API_KEY"), !dotEnvKey.isEmpty {
            key = dotEnvKey
            logger.info("Deepgram API key .env dosyasindan alindi")
        } else {
            key = nil
        }

        guard let apiKey = key else {
            logger.warning(
                "DEEPGRAM_API_KEY bulunamadi — deepgramKeyOverride, scheme env var veya .env dosyasi kullanin"
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

    /// Repo root'taki .env dosyasindan key okur.
    /// #filePath ile derleme zamaninda kaynak dosya yolu bulunur, oradan repo root hesaplanir.
    private static func readFromDotEnv(_ key: String, filePath: String = #filePath) -> String? {
        // DebugSetup.swift: apps/ios/RafRaf/App/DebugSetup.swift
        // Repo root: 5 seviye yukari
        var url = URL(fileURLWithPath: filePath)
        for _ in 0..<5 { url.deleteLastPathComponent() }
        let envURL = url.appendingPathComponent(".env")

        guard let contents = try? String(contentsOf: envURL, encoding: .utf8) else {
            return nil
        }

        for line in contents.components(separatedBy: .newlines) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty, !trimmed.hasPrefix("#") else { continue }
            let parts = trimmed.split(separator: "=", maxSplits: 1)
            guard parts.count == 2, String(parts[0]) == key else { continue }
            let value = String(parts[1]).trimmingCharacters(in: .whitespaces)
            if !value.isEmpty {
                logger.debug("\(key) .env dosyasindan okundu")
                return value
            }
        }
        return nil
    }
}
#endif
