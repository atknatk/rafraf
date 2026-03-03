import AVFoundation
import Foundation
import os

/// Voice input ViewModel.
/// Ses kaydi yasamdongusu, transkripsiyon gosterimi ve dil secimi yonetimi.
@Observable
@MainActor
final class VoiceInputViewModel {
    // MARK: - State

    /// Mevcut ses giris durumu.
    var state: VoiceInputState = .idle
    /// Gercek zamanli interim transkripsiyon metni.
    var interimTranscription: String = ""
    /// Son final transkripsiyon metni.
    var finalTranscription: String = ""
    /// Aktif ses seviyesi (waveform icin).
    var audioLevel: AudioLevel = AudioLevel(averagePower: -160, peakPower: -160, normalizedLevel: 0)
    /// Secili dil.
    var selectedLanguage: VoiceLanguage = .defaultLanguage
    /// Hata mesaji (kullaniciya gosterilecek).
    var errorMessage: String?

    // MARK: - Private

    private let startRecordingUseCase: StartVoiceRecordingUseCase
    private let stopRecordingUseCase: StopVoiceRecordingUseCase
    private let audioSessionManager: RFAudioSessionManager
    private var transcriptionTask: Task<Void, Never>?
    private var audioLevelTask: Task<Void, Never>?
    private let logger = AppLogger.logger(for: "VoiceInput")

    /// Transkripsiyon tamamlandiginda donen callback.
    /// Chat ekrani bu callback ile final metni alir.
    var onTranscriptionComplete: ((String) -> Void)?

    // MARK: - Init

    init(
        startRecordingUseCase: StartVoiceRecordingUseCase,
        stopRecordingUseCase: StopVoiceRecordingUseCase,
        audioSessionManager: RFAudioSessionManager
    ) {
        self.startRecordingUseCase = startRecordingUseCase
        self.stopRecordingUseCase = stopRecordingUseCase
        self.audioSessionManager = audioSessionManager

        // Kaydedilmis dil tercihini yukle
        loadSavedLanguage()
        logger.info("VoiceInputViewModel baslatildi - dil: \(selectedLanguage.rawValue)")
    }

    // MARK: - Actions

    /// Ses kaydini baslatir.
    func startRecording() async {
        guard state == .idle || isErrorState else {
            logger.warning("Kayit baslatma reddedildi - mevcut durum: \(String(describing: state))")
            return
        }

        state = .requesting
        errorMessage = nil
        interimTranscription = ""
        finalTranscription = ""

        do {
            let stream = try await startRecordingUseCase.execute(language: selectedLanguage)
            state = .recording
            logger.info("Ses kaydi baslatildi")

            // Ses seviyesi izlemeyi baslat
            startAudioLevelMonitoring()

            // Transkripsiyon stream'ini dinle
            transcriptionTask = Task {
                for await result in stream {
                    await handleTranscriptionResult(result)
                }
            }
        } catch {
            handleStartError(error)
        }
    }

    /// Ses kaydini durdurur ve final transkripsiyon'u gonderir.
    func stopRecording() async {
        guard state == .recording else {
            logger.warning("Kayit durdurma reddedildi - mevcut durum: \(String(describing: state))")
            return
        }

        state = .processing
        logger.info("Ses kaydi durduruluyor...")

        // Streaming'i durdur
        await stopRecordingUseCase.execute()
        transcriptionTask?.cancel()
        transcriptionTask = nil
        audioLevelTask?.cancel()
        audioLevelTask = nil
        audioLevel = AudioLevel(averagePower: -160, peakPower: -160, normalizedLevel: 0)

        // Final transkripsiyon kontrolu
        let transcription = buildFinalTranscription()
        if transcription.isEmpty {
            state = .error(.emptyTranscription)
            errorMessage = VoiceInputError.emptyTranscription.localizedMessage
            logger.warning("Bos transkripsiyon - ses algilanamadi")

            // 2 saniye sonra idle'a don
            Task {
                try? await Task.sleep(for: .seconds(2))
                state = .idle
                errorMessage = nil
            }
        } else {
            finalTranscription = transcription
            onTranscriptionComplete?(transcription)
            logger.info("Transkripsiyon tamamlandi: \(transcription.prefix(50))...")
            state = .idle
        }

        interimTranscription = ""
    }

    /// Kaydi iptal eder (mesaj gondermeden durdurur).
    func cancelRecording() async {
        await stopRecordingUseCase.execute()
        transcriptionTask?.cancel()
        transcriptionTask = nil
        audioLevelTask?.cancel()
        audioLevelTask = nil
        audioLevel = AudioLevel(averagePower: -160, peakPower: -160, normalizedLevel: 0)
        interimTranscription = ""
        state = .idle
        logger.info("Ses kaydi iptal edildi")
    }

    /// Dil secimini degistirir.
    /// - Parameter language: Yeni dil.
    func changeLanguage(_ language: VoiceLanguage) {
        selectedLanguage = language
        saveLanguagePreference(language)
        logger.info("Dil degistirildi: \(language.rawValue)")
    }

    /// Hata mesajini temizler.
    func dismissError() {
        errorMessage = nil
        if isErrorState {
            state = .idle
        }
    }

    // MARK: - Computed

    /// Kayit yapiliyor mu.
    var isRecording: Bool {
        state == .recording
    }

    /// Hata durumunda mi.
    var isErrorState: Bool {
        if case .error = state { return true }
        return false
    }

    /// Mikrofon izni verilmis mi.
    var hasMicrophonePermission: Bool {
        audioSessionManager.hasPermission
    }

    // MARK: - Private

    private func handleTranscriptionResult(_ result: TranscriptionResult) async {
        if result.isFinal {
            // Final sonucu birikimli transkripsiyon'a ekle
            if !finalTranscription.isEmpty {
                finalTranscription += " "
            }
            finalTranscription += result.text
            interimTranscription = ""
            logger.debug("Final transkripsiyon parcasi: \(result.text)")
        } else {
            // Interim sonucu guncelle
            interimTranscription = result.text
        }
    }

    private func buildFinalTranscription() -> String {
        var result = finalTranscription
        if !interimTranscription.isEmpty {
            if !result.isEmpty {
                result += " "
            }
            result += interimTranscription
        }
        return result.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func handleStartError(_ error: Error) {
        logger.error("Kayit baslatma hatasi: \(error.localizedDescription)")

        if let repoError = error as? VoiceInputRepositoryError {
            switch repoError {
            case .microphonePermissionDenied:
                state = .error(.microphonePermissionDenied)
                errorMessage = VoiceInputError.microphonePermissionDenied.localizedMessage
            case .connectionFailed:
                state = .error(.deepgramConnectionFailed)
                errorMessage = VoiceInputError.deepgramConnectionFailed.localizedMessage
            case .audioCaptureError:
                state = .error(.audioSessionError)
                errorMessage = VoiceInputError.audioSessionError.localizedMessage
            }
        } else {
            state = .error(.transcriptionFailed)
            errorMessage = VoiceInputError.transcriptionFailed.localizedMessage
        }
    }

    private func startAudioLevelMonitoring() {
        // AudioSessionManager zaten levelCallback ile bildirim yapiyor
        // Burada ek izleme gerekirse eklenebilir
    }

    private func loadSavedLanguage() {
        if let saved = UserDefaults.standard.string(forKey: VoiceLanguage.storageKey),
           let language = VoiceLanguage(rawValue: saved) {
            selectedLanguage = language
        }
    }

    private func saveLanguagePreference(_ language: VoiceLanguage) {
        UserDefaults.standard.set(language.rawValue, forKey: VoiceLanguage.storageKey)
    }
}
