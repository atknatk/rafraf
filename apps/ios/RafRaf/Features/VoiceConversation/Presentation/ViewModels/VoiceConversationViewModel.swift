import Factory
import Foundation
import os

/// Ses konusma modu state'leri.
enum VoiceConversationState: Sendable, Equatable {
    /// Bekleme — voice mode acik ama pasif.
    case idle
    /// Kullanici konusuyor, Deepgram STT aktif.
    case listening
    /// Sessizlik algilandi, mesaj gonderildi, cevap bekleniyor.
    case processing
    /// AI cevabi geliyor (streaming text + audio).
    case aiSpeaking
    /// Kullanici barge-in yapti, AI durduruluyor.
    case interrupted
}

/// Interaktif sesli konusma modu ViewModel.
/// ChatGPT benzeri sureksiz voice chat deneyimi saglar:
/// konusma → sessizlik → otomatik gonderim → streaming text + TTS → barge-in.
@Observable
@MainActor
final class VoiceConversationViewModel {
    // MARK: - State

    /// Mevcut konusma durumu.
    var state: VoiceConversationState = .idle
    /// Canli kullanici transkripsiyon metni.
    var transcription: String = ""
    /// Interim (gecici) transkripsiyon metni.
    var interimText: String = ""
    /// Streaming AI cevap metni.
    var aiResponseText: String = ""
    /// Ses seviyesi (waveform icin).
    var audioLevel: Float = 0
    /// Hata mesaji.
    var errorMessage: String?
    /// Secili dil.
    var selectedLanguage: VoiceLanguage = .defaultLanguage

    // MARK: - Dependencies

    private let voiceInputVM: VoiceInputViewModel
    private let webSocketManager: WebSocketConnectionManager
    private let streamingAudioPlayer: StreamingAudioPlayer
    private let chatViewModel: ChatViewModel
    private let logger = AppLogger.logger(for: "VoiceConversation")

    // MARK: - Private

    private var silenceTimer: Task<Void, Never>?
    private var currentMessageId: String?
    private var audioLevelObservationTask: Task<Void, Never>?

    /// Sessizlik suresi (saniye) — otomatik gonderim icin.
    private let silenceThreshold: TimeInterval = 1.5

    // MARK: - Init

    init(
        voiceInputVM: VoiceInputViewModel,
        webSocketManager: WebSocketConnectionManager,
        streamingAudioPlayer: StreamingAudioPlayer,
        chatViewModel: ChatViewModel
    ) {
        self.voiceInputVM = voiceInputVM
        self.webSocketManager = webSocketManager
        self.streamingAudioPlayer = streamingAudioPlayer
        self.chatViewModel = chatViewModel

        // Audio chunk oynatim tamamlanma callback
        streamingAudioPlayer.onAllChunksPlayed = { [weak self] in
            Task { @MainActor [weak self] in
                self?.handleAudioPlaybackFinished()
            }
        }

        loadSavedLanguage()
        logger.info("VoiceConversationViewModel baslatildi")
    }

    // MARK: - Public Actions

    /// Voice mode'u baslatir ve dinlemeye baslar.
    func enterVoiceMode() async {
        state = .idle
        transcription = ""
        aiResponseText = ""
        interimText = ""
        errorMessage = nil

        // WebSocket streaming handler'larini kaydet
        await registerStreamingHandlers()

        // Dinlemeye basla
        await startListening()
    }

    /// Voice mode'dan cikar.
    func exitVoiceMode() async {
        silenceTimer?.cancel()
        silenceTimer = nil
        audioLevelObservationTask?.cancel()
        audioLevelObservationTask = nil
        streamingAudioPlayer.stopAndClear()

        if voiceInputVM.isRecording {
            await voiceInputVM.cancelRecording()
        }

        // Handler'lari kaldir
        await unregisterStreamingHandlers()

        state = .idle
        currentMessageId = nil
        logger.info("Voice mode sonlandirildi")
    }

    /// Kullanici barge-in (AI konusurken kesme).
    func handleBargeIn() async {
        guard state == .aiSpeaking else { return }
        state = .interrupted
        logger.info("Barge-in basladi")

        // 1. Ses oynatimi durdur
        streamingAudioPlayer.stopAndClear()

        // 2. Interrupt mesaji gonder
        let interrupt = WebSocketMessageFactory.voiceInterruptMessage(
            sessionId: webSocketManager.connectionState == .connected ? nil : nil
        )
        do {
            try await webSocketManager.sendMessage(interrupt)
        } catch {
            logger.error("Interrupt gonderilemedi: \(error.localizedDescription)")
        }

        // 3. Tekrar dinlemeye basla
        aiResponseText = ""
        currentMessageId = nil
        await startListening()
    }

    /// Dil degistirir.
    func changeLanguage(_ language: VoiceLanguage) {
        selectedLanguage = language
        voiceInputVM.changeLanguage(language)
        UserDefaults.standard.set(language.rawValue, forKey: VoiceLanguage.storageKey)
    }

    // MARK: - Private — Dinleme

    private func startListening() async {
        state = .listening
        transcription = ""
        interimText = ""
        errorMessage = nil

        // Voice input callback — her transkripsiyon parcasi icin
        voiceInputVM.onTranscriptionComplete = { [weak self] fullTranscription in
            guard let self else { return }
            // stopRecording cagirildiginda bu callback gelir
            // Ancak biz silence detection ile kendimiz yonetiyoruz
        }

        // Ses kaydini baslat
        await voiceInputVM.startRecording()

        // Ses seviyesi ve transkripsiyon takibi
        startObservingVoiceInput()
    }

    private func startObservingVoiceInput() {
        audioLevelObservationTask?.cancel()
        audioLevelObservationTask = Task { [weak self] in
            guard let self else { return }

            while !Task.isCancelled {
                let level = voiceInputVM.audioLevel.normalizedLevel
                let interim = voiceInputVM.interimTranscription
                let final_ = voiceInputVM.finalTranscription

                audioLevel = level

                // Final transkripsiyon parcasi geldi
                if !final_.isEmpty && final_ != transcription {
                    transcription = final_
                    interimText = ""
                    resetSilenceTimer()
                }

                // Interim guncelle
                if !interim.isEmpty {
                    interimText = interim
                }

                try? await Task.sleep(for: .milliseconds(50))
            }
        }
    }

    // MARK: - Private — Sessizlik Algilama

    private func resetSilenceTimer() {
        silenceTimer?.cancel()
        silenceTimer = Task { [weak self] in
            do {
                try await Task.sleep(for: .seconds(self?.silenceThreshold ?? 1.5))
                guard !Task.isCancelled else { return }
                await self?.autoSend()
            } catch {
                // Task cancelled — normal
            }
        }
    }

    private func autoSend() async {
        let text = buildFinalText()
        guard !text.isEmpty else {
            // Bos konusma — dinlemeye devam
            return
        }

        state = .processing
        silenceTimer?.cancel()
        audioLevelObservationTask?.cancel()

        // Kaydi durdur (callback'i tetiklemeden)
        await voiceInputVM.cancelRecording()

        // Kullanici mesajini chat'e ekle
        chatViewModel.handleIncomingMessage(ChatMessage(
            content: text,
            sender: .user,
            type: .text
        ))

        // Backend'e voice mesaj olarak gonder (TTS streaming tetikler)
        let voiceMessage = WebSocketMessageFactory.voiceMessage(text)
        do {
            try await webSocketManager.sendMessage(voiceMessage)
            logger.info("Sesli mesaj gonderildi: \(text.prefix(50))")
        } catch {
            errorMessage = String(localized: "voice.error.sendFailed")
            logger.error("Sesli mesaj gonderilemedi: \(error.localizedDescription)")
            // Tekrar dinlemeye basla
            await startListening()
        }
    }

    private func buildFinalText() -> String {
        var result = transcription
        if !interimText.isEmpty {
            if !result.isEmpty { result += " " }
            result += interimText
        }
        return result.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - Private — Streaming Handlers

    private func registerStreamingHandlers() async {
        // Chat stream delta
        let deltaHandler = VoiceStreamDeltaHandler { [weak self] messageId, delta in
            Task { @MainActor [weak self] in
                self?.handleStreamDelta(messageId: messageId, delta: delta)
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.chatStream.rawValue,
            handler: deltaHandler
        )

        // Chat stream end
        let endHandler = VoiceStreamEndHandler { [weak self] messageId, fullText in
            Task { @MainActor [weak self] in
                self?.handleStreamEnd(messageId: messageId, fullText: fullText)
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.chatStreamEnd.rawValue,
            handler: endHandler
        )

        // Voice audio chunk
        let audioHandler = VoiceAudioChunkHandler { [weak self] content in
            Task { @MainActor [weak self] in
                self?.handleAudioChunk(content)
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.voiceAudioChunk.rawValue,
            handler: audioHandler
        )

        // Voice audio end
        let audioEndHandler = VoiceAudioEndHandler { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.logger.debug("Ses akisi tamamlandi")
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.voiceAudioEnd.rawValue,
            handler: audioEndHandler
        )
    }

    private func unregisterStreamingHandlers() async {
        await webSocketManager.unregisterHandler(type: WebSocketMessageType.chatStream.rawValue)
        await webSocketManager.unregisterHandler(type: WebSocketMessageType.chatStreamEnd.rawValue)
        await webSocketManager.unregisterHandler(type: WebSocketMessageType.voiceAudioChunk.rawValue)
        await webSocketManager.unregisterHandler(type: WebSocketMessageType.voiceAudioEnd.rawValue)
    }

    // MARK: - Private — Stream Event Handlers

    private func handleStreamDelta(messageId: String, delta: String) {
        currentMessageId = messageId
        state = .aiSpeaking
        aiResponseText += delta

        // ChatViewModel'e de ilet (chat gecmisi icin)
        chatViewModel.handleStreamDelta(messageId: messageId, delta: delta)
    }

    private func handleStreamEnd(messageId: String, fullText: String) {
        aiResponseText = fullText
        chatViewModel.handleStreamEnd(messageId: messageId, fullText: fullText, type: .text)
        // Audio hala oynuyor olabilir — onAllChunksPlayed callback'i bekle
    }

    private func handleAudioChunk(_ content: VoiceAudioChunkContent) {
        streamingAudioPlayer.enqueueChunk(
            base64Audio: content.audioData,
            sentenceText: content.sentenceText
        )
    }

    private func handleAudioPlaybackFinished() {
        guard state == .aiSpeaking else { return }
        logger.info("AI ses oynatimi tamamlandi, tekrar dinlemeye geciliyor")

        // AI bitti → tekrar dinlemeye basla
        aiResponseText = ""
        currentMessageId = nil
        Task {
            await startListening()
        }
    }

    // MARK: - Private — Util

    private func loadSavedLanguage() {
        if let saved = UserDefaults.standard.string(forKey: VoiceLanguage.storageKey),
           let language = VoiceLanguage(rawValue: saved) {
            selectedLanguage = language
        }
    }
}

// MARK: - WebSocket Handlers

/// Streaming text delta handler (voice mode).
private final class VoiceStreamDeltaHandler: WebSocketMessageHandler {
    private let onDelta: @Sendable (String, String) -> Void

    init(onDelta: @escaping @Sendable (String, String) -> Void) {
        self.onDelta = onDelta
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .chatStream(let content) = message.content else { return }
        onDelta(content.messageId, content.delta)
    }
}

/// Stream tamamlanma handler (voice mode).
private final class VoiceStreamEndHandler: WebSocketMessageHandler {
    private let onEnd: @Sendable (String, String) -> Void

    init(onEnd: @escaping @Sendable (String, String) -> Void) {
        self.onEnd = onEnd
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .chatStreamEnd(let content) = message.content else { return }
        onEnd(content.messageId, content.fullText)
    }
}

/// Voice audio chunk handler.
private final class VoiceAudioChunkHandler: WebSocketMessageHandler {
    private let onChunk: @Sendable (VoiceAudioChunkContent) -> Void

    init(onChunk: @escaping @Sendable (VoiceAudioChunkContent) -> Void) {
        self.onChunk = onChunk
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .voiceAudioChunk(let content) = message.content else { return }
        onChunk(content)
    }
}

/// Voice audio end handler.
private final class VoiceAudioEndHandler: WebSocketMessageHandler {
    private let onEnd: @Sendable (String) -> Void

    init(onEnd: @escaping @Sendable (String) -> Void) {
        self.onEnd = onEnd
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .voiceAudioEnd(let content) = message.content else { return }
        onEnd(content.messageId)
    }
}
