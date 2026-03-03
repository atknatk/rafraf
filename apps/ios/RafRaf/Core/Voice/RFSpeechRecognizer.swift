@preconcurrency import AVFoundation
import Foundation
import os

/// Deepgram STT WebSocket entegrasyonu.
/// Ses verisi streaming olarak Deepgram'a gonderilir, transkripsiyon sonuclari alinir.
final class RFSpeechRecognizer: NSObject, @unchecked Sendable {
    private let keychainHelper: KeychainHelper
    private let logger = AppLogger.logger(for: "SpeechRecognizer")

    private var webSocketTask: URLSessionWebSocketTask?
    private var urlSession: URLSession?
    private var transcriptionContinuation: AsyncStream<DeepgramTranscriptDTO>.Continuation?
    private var isActive: Bool = false

    /// Deepgram API Key keychain anahtari.
    static let deepgramAPIKeyKeychainKey = "com.rafraf.deepgram.apiKey"

    init(keychainHelper: KeychainHelper) {
        self.keychainHelper = keychainHelper
        super.init()
    }

    // MARK: - Public

    /// Deepgram WebSocket baglantisi kurar ve transkripsiyon sonuclarini yayan stream dondurur.
    /// - Parameter language: Transkripsiyon dili.
    /// - Returns: DeepgramTranscriptDTO stream.
    func connect(language: VoiceLanguage) async throws -> AsyncStream<DeepgramTranscriptDTO> {
        guard !isActive else {
            logger.warning("Deepgram baglantisi zaten aktif")
            throw DeepgramError.alreadyConnected
        }

        guard let apiKey = keychainHelper.readString(for: Self.deepgramAPIKeyKeychainKey) else {
            logger.error("Deepgram API key bulunamadi")
            throw DeepgramError.apiKeyMissing
        }

        let url = buildDeepgramURL(language: language)
        logger.info("Deepgram'a baglaniliyor: \(url.absoluteString)")

        let configuration = URLSessionConfiguration.default
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
        self.urlSession = session

        var request = URLRequest(url: url)
        request.setValue("Token \(apiKey)", forHTTPHeaderField: "Authorization")

        let task = session.webSocketTask(with: request)
        self.webSocketTask = task
        task.resume()
        isActive = true

        let stream = AsyncStream<DeepgramTranscriptDTO> { [weak self] continuation in
            self?.transcriptionContinuation = continuation
            continuation.onTermination = { @Sendable [weak self] _ in
                self?.logger.info("Transkripsiyon stream sonlandirildi")
            }
        }

        // Mesaj dinleme dongusunu baslat
        startReceiving()

        logger.info("Deepgram baglantisi kuruldu - dil: \(language.rawValue)")
        return stream
    }

    /// Ses verisini Deepgram'a gonderir.
    /// - Parameter buffer: PCM ses buffer'i (16kHz, mono, 16-bit).
    func sendAudio(buffer: AVAudioPCMBuffer) {
        guard isActive, let webSocketTask else { return }

        guard let data = bufferToData(buffer) else {
            logger.warning("Ses buffer'i veriye donusturulemedi")
            return
        }

        let message = URLSessionWebSocketTask.Message.data(data)
        webSocketTask.send(message) { [weak self] error in
            if let error {
                self?.logger.error("Ses gonderme hatasi: \(error.localizedDescription)")
            }
        }
    }

    /// Deepgram baglantisini kapatir.
    func disconnect() async {
        guard isActive else { return }
        isActive = false

        // CloseStream mesaji gonder
        let closeMessage = DeepgramCloseStreamDTO()
        if let data = try? JSONEncoder().encode(closeMessage),
           let jsonString = String(data: data, encoding: .utf8) {
            let message = URLSessionWebSocketTask.Message.string(jsonString)
            try? await webSocketTask?.send(message)
        }

        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        transcriptionContinuation?.finish()
        transcriptionContinuation = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil
        logger.info("Deepgram baglantisi kapatildi")
    }

    /// Baglanti aktif mi.
    var connected: Bool {
        isActive
    }

    // MARK: - Private

    private func buildDeepgramURL(language: VoiceLanguage) -> URL {
        var components = URLComponents()
        components.scheme = "wss"
        components.host = "api.deepgram.com"
        components.path = "/v1/listen"
        components.queryItems = [
            URLQueryItem(name: "model", value: "nova-2"),
            URLQueryItem(name: "language", value: language.deepgramCode),
            URLQueryItem(name: "smart_format", value: "true"),
            URLQueryItem(name: "punctuate", value: "true"),
            URLQueryItem(name: "interim_results", value: "true"),
            URLQueryItem(name: "endpointing", value: "500"),
            URLQueryItem(name: "vad_events", value: "true"),
            URLQueryItem(name: "encoding", value: "linear16"),
            URLQueryItem(name: "sample_rate", value: "16000"),
            URLQueryItem(name: "channels", value: "1"),
        ]

        // URLComponents ile olusturulan URL her zaman gecerli olmalidir.
        // Yine de guvenli erisim sagliyoruz.
        guard let url = components.url else {
            // Static URL her zaman gecerlidir, guard sadece guvenlik icin
            guard let fallback = URL(string: "wss://api.deepgram.com/v1/listen") else {
                fatalError("Sabit Deepgram URL'i olusturulamadi — bu bir programlama hatasidir")
            }
            return fallback
        }
        return url
    }

    private func startReceiving() {
        webSocketTask?.receive { [weak self] result in
            guard let self, self.isActive else { return }

            switch result {
            case .success(let message):
                self.handleMessage(message)
                // Sonraki mesaji dinle
                self.startReceiving()

            case .failure(let error):
                self.logger.error("WebSocket mesaj alma hatasi: \(error.localizedDescription)")
                self.transcriptionContinuation?.finish()
            }
        }
    }

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
        switch message {
        case .string(let text):
            guard let data = text.data(using: .utf8) else { return }
            decodeMessage(data)

        case .data(let data):
            decodeMessage(data)

        @unknown default:
            logger.warning("Bilinmeyen WebSocket mesaj tipi alindi")
        }
    }

    private func decodeMessage(_ data: Data) {
        // Mesaj tipini kontrol et
        struct MessageType: Codable {
            let type: String
        }

        guard let messageType = try? JSONDecoder().decode(MessageType.self, from: data) else {
            logger.warning("Mesaj tipi cozumlenemedi")
            return
        }

        switch messageType.type {
        case "Results":
            guard let transcript = try? JSONDecoder().decode(DeepgramTranscriptDTO.self, from: data) else {
                logger.warning("Transkripsiyon DTO cozumlenemedi")
                return
            }
            transcriptionContinuation?.yield(transcript)

        case "Metadata":
            logger.info("Deepgram metadata alindi")

        default:
            logger.debug("Bilinmeyen Deepgram mesaj tipi: \(messageType.type)")
        }
    }

    private func bufferToData(_ buffer: AVAudioPCMBuffer) -> Data? {
        let frameLength = Int(buffer.frameLength)
        guard frameLength > 0 else { return nil }

        // Int16 format kontrol
        if let int16Data = buffer.int16ChannelData {
            let channelData = int16Data.pointee
            let byteCount = frameLength * MemoryLayout<Int16>.size
            return Data(bytes: channelData, count: byteCount)
        }

        return nil
    }
}

// MARK: - URLSessionWebSocketDelegate

extension RFSpeechRecognizer: URLSessionWebSocketDelegate {
    func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didOpenWithProtocol protocol: String?
    ) {
        logger.info("Deepgram WebSocket baglantisi acildi")
    }

    func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
        reason: Data?
    ) {
        logger.info("Deepgram WebSocket kapatildi - kod: \(closeCode.rawValue)")
        isActive = false
        transcriptionContinuation?.finish()
    }
}

/// Deepgram hatalari.
enum DeepgramError: Error, Sendable {
    case apiKeyMissing
    case alreadyConnected
    case connectionFailed
}
