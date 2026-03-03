import AVFoundation
import Foundation
import os

/// Voice input repository implementasyonu.
/// Deepgram WebSocket ve AVAudioEngine koordinasyonu.
final class VoiceInputRepositoryImpl: VoiceInputRepositoryProtocol, @unchecked Sendable {
    private let speechRecognizer: RFSpeechRecognizer
    private let audioSessionManager: RFAudioSessionManager
    private let logger = AppLogger.logger(for: "VoiceInputRepository")

    private var activeLanguage: VoiceLanguage = .turkish

    init(
        speechRecognizer: RFSpeechRecognizer,
        audioSessionManager: RFAudioSessionManager
    ) {
        self.speechRecognizer = speechRecognizer
        self.audioSessionManager = audioSessionManager
    }

    // MARK: - VoiceInputRepositoryProtocol

    var isConnected: Bool {
        speechRecognizer.connected
    }

    func startStreaming(language: VoiceLanguage) async throws -> AsyncStream<TranscriptionResult> {
        activeLanguage = language

        // Mikrofon izni kontrolu
        if !audioSessionManager.hasPermission {
            let granted = await audioSessionManager.requestPermission()
            if !granted {
                logger.error("Mikrofon izni reddedildi")
                throw VoiceInputRepositoryError.microphonePermissionDenied
            }
        }

        // Deepgram baglantisi kur
        let deepgramStream: AsyncStream<DeepgramTranscriptDTO>
        do {
            deepgramStream = try await speechRecognizer.connect(language: language)
        } catch {
            logger.error("Deepgram baglanti hatasi: \(error.localizedDescription)")
            throw VoiceInputRepositoryError.connectionFailed
        }

        // Ses capture baslat — buffer'lari Deepgram'a gonder
        do {
            try audioSessionManager.startCapture(
                bufferCallback: { [weak self] buffer in
                    self?.speechRecognizer.sendAudio(buffer: buffer)
                },
                levelCallback: { _ in
                    // Audio level ViewModel tarafindan ayri yonetilir
                }
            )
        } catch {
            logger.error("Ses capture baslatma hatasi: \(error.localizedDescription)")
            await speechRecognizer.disconnect()
            throw VoiceInputRepositoryError.audioCaptureError
        }

        logger.info("Voice streaming baslatildi - dil: \(language.rawValue)")

        // Deepgram DTO stream'ini Domain model stream'ine donustur
        return AsyncStream<TranscriptionResult> { continuation in
            Task {
                for await dto in deepgramStream {
                    if let result = TranscriptionMapper.toDomain(from: dto, language: language) {
                        continuation.yield(result)
                    }
                }
                continuation.finish()
            }
        }
    }

    func stopStreaming() async {
        audioSessionManager.stopCapture()
        await speechRecognizer.disconnect()
        logger.info("Voice streaming durduruldu")
    }
}

/// Voice input repository hatalari.
enum VoiceInputRepositoryError: Error, Sendable {
    case microphonePermissionDenied
    case connectionFailed
    case audioCaptureError
}
