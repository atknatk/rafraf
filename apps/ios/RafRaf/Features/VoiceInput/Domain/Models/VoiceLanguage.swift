import Foundation

/// Desteklenen sesli giris dilleri.
/// Deepgram STT icin kullanilacak dil secenekleri.
enum VoiceLanguage: String, Sendable, Equatable, CaseIterable {
    /// Turkce.
    case turkish = "tr"
    /// Ingilizce.
    case english = "en"

    /// Goruntuleme adi.
    var displayName: String {
        switch self {
        case .turkish:
            return String(localized: "voiceInput.language.turkish")
        case .english:
            return String(localized: "voiceInput.language.english")
        }
    }

    /// Deepgram API icin dil kodu.
    var deepgramCode: String {
        rawValue
    }

    /// UserDefaults key.
    static let storageKey = "com.rafraf.voiceInput.selectedLanguage"

    /// Varsayilan dil: Turkce.
    static let defaultLanguage: VoiceLanguage = .turkish
}
