import Foundation

/// TTS ses secenekleri.
/// OpenAI TTS API'nin destekledigi sesler.
enum TTSVoice: String, Sendable, CaseIterable, Codable {
    case alloy
    case echo
    case fable
    case onyx
    case nova
    case shimmer

    /// Ses aciklamasi (lokalize).
    var displayName: String {
        switch self {
        case .alloy:
            return String(localized: "voiceOutput.voice.alloy")
        case .echo:
            return String(localized: "voiceOutput.voice.echo")
        case .fable:
            return String(localized: "voiceOutput.voice.fable")
        case .onyx:
            return String(localized: "voiceOutput.voice.onyx")
        case .nova:
            return String(localized: "voiceOutput.voice.nova")
        case .shimmer:
            return String(localized: "voiceOutput.voice.shimmer")
        }
    }

    /// UserDefaults saklama anahtari.
    static let storageKey = "voiceOutput.selectedVoice"
}
