import Foundation

/// Ses cikis durumu.
/// Oynatma yasamdongusu state machine: idle -> loading -> playing -> paused -> idle.
enum VoiceOutputState: Sendable, Equatable {
    /// Bekleme durumu, ses oynatilmiyor.
    case idle
    /// Ses verisi yukleniyor (TTS API'den).
    case loading
    /// Ses oynatiliyor.
    case playing
    /// Ses duraklatildi.
    case paused
    /// Bir hata olustu.
    case error(VoiceOutputError)
}

/// Ses cikis hatalari.
enum VoiceOutputError: Sendable, Equatable {
    /// TTS API istegi basarisiz.
    case ttsRequestFailed
    /// Ses verisi decode edilemedi.
    case audioDecodingFailed
    /// Ses oynatma hatasi.
    case playbackFailed
    /// Ag baglantisi yok.
    case networkUnavailable
    /// Bos metin gonderildi.
    case emptyText

    /// Kullaniciya gosterilecek lokalize hata mesaji.
    var localizedMessage: String {
        switch self {
        case .ttsRequestFailed:
            return String(localized: "voiceOutput.error.ttsRequestFailed")
        case .audioDecodingFailed:
            return String(localized: "voiceOutput.error.audioDecodingFailed")
        case .playbackFailed:
            return String(localized: "voiceOutput.error.playbackFailed")
        case .networkUnavailable:
            return String(localized: "voiceOutput.error.networkUnavailable")
        case .emptyText:
            return String(localized: "voiceOutput.error.emptyText")
        }
    }
}
