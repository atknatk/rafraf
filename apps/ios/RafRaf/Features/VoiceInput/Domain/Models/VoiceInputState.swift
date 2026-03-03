import Foundation

/// Ses giris durumu.
/// Kayit yasamdongusu state machine'i: idle -> requesting -> recording -> processing -> idle.
enum VoiceInputState: Sendable, Equatable {
    /// Bekleme durumu, kayit yapilmiyor.
    case idle
    /// Mikrofon izni isteniyor.
    case requesting
    /// Ses kaydediliyor ve Deepgram'a streaming yapiliyor.
    case recording
    /// Son ses parcalari isleniyor, final transkripsiyon bekleniyor.
    case processing
    /// Bir hata olustu.
    case error(VoiceInputError)
}

/// Ses giris hatalari.
enum VoiceInputError: Sendable, Equatable {
    /// Mikrofon erisim izni reddedildi.
    case microphonePermissionDenied
    /// Deepgram WebSocket baglantisi kurulamadi.
    case deepgramConnectionFailed
    /// Internet baglantisi yok.
    case networkUnavailable
    /// AVAudioSession yapilandirma hatasi.
    case audioSessionError
    /// Transkripsiyon isleme hatasi.
    case transcriptionFailed
    /// Bos transkripsiyon — ses algilanamadi.
    case emptyTranscription

    /// Kullaniciya gosterilecek lokalize hata mesaji.
    var localizedMessage: String {
        switch self {
        case .microphonePermissionDenied:
            return String(localized: "voiceInput.error.microphonePermissionDenied")
        case .deepgramConnectionFailed:
            return String(localized: "voiceInput.error.connectionFailed")
        case .networkUnavailable:
            return String(localized: "voiceInput.error.networkUnavailable")
        case .audioSessionError:
            return String(localized: "voiceInput.error.audioSession")
        case .transcriptionFailed:
            return String(localized: "voiceInput.error.transcriptionFailed")
        case .emptyTranscription:
            return String(localized: "voiceInput.error.emptyTranscription")
        }
    }
}
