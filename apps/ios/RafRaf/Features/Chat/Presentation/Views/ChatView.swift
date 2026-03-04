import Factory
import SwiftUI

/// Sohbet ekrani — Claude-inspired sicak ve temiz gorunum.
/// Kullanicinin AI asistan ile sesli ve metin tabanli iletisim kurdugu ana ekran.
struct ChatView: View {
    @State private var viewModel: ChatViewModel
    @State private var voiceInputViewModel = Container.shared.voiceInputViewModel()
    @State private var voiceOutputViewModel = Container.shared.voiceOutputViewModel()
    @State private var showVoiceOverlay = false
    @State private var showVoiceConversation = false
    private let webSocketManager = Container.shared.webSocketConnectionManager()

    init(viewModel: ChatViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                messageListView

                // Ses kaydi overlay'i — chat input'un ustunde gosterilir
                if showVoiceOverlay {
                    RFVoiceInputView(viewModel: voiceInputViewModel)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                        .background(RFColors.fallbackSurface)
                }

                chatInputView
            }
            .background(RFColors.fallbackBackground)
            .navigationTitle(String(localized: "chat.title"))
            .navigationBarTitleDisplayMode(.inline)
            .task {
                setupVoiceCallbacks()
                await registerMessageHandlers()
                if webSocketManager.isConnected {
                    await viewModel.loadHistory()
                }
            }
            .onChange(of: webSocketManager.isConnected) { _, isConnected in
                if isConnected {
                    Task { await viewModel.loadHistory() }
                }
            }
            .overlay {
                if let errorMessage = viewModel.errorMessage {
                    errorBanner(message: errorMessage)
                }
            }
            .animation(RFAnimation.springResponsive, value: showVoiceOverlay)
            .fullScreenCover(isPresented: $showVoiceConversation) {
                let voiceVM = Container.shared.voiceConversationViewModel()
                VoiceConversationView(viewModel: voiceVM) {
                    showVoiceConversation = false
                }
                .task {
                    await voiceVM.enterVoiceMode()
                }
            }
        }
    }

    // MARK: - Message List

    @ViewBuilder
    private var messageListView: some View {
        if viewModel.isLoading {
            ChatSkeletonView()
        } else if viewModel.messages.isEmpty {
            Spacer()
            RFEmptyStateView(
                systemImage: "message",
                title: String(localized: "chat.empty.title"),
                message: String(localized: "chat.empty.message")
            )
            Spacer()
        } else {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: RFSpacing.sm) {
                        if viewModel.hasMoreMessages {
                            loadMoreButton
                        }

                        ForEach(viewModel.messages) { message in
                            RFMessageBubble(
                                message: message,
                                onCopy: { viewModel.copyMessage($0) },
                                onSpeak: message.sender == .assistant
                                    ? { Task { await voiceOutputViewModel.speak(text: message.content) } }
                                    : nil
                            )
                            .id(message.id)
                            .transition(RFTransition.chatMessage)
                        }

                        if viewModel.isTyping {
                            RFTypingIndicator()
                                .id("typing-indicator")
                        }
                    }
                    .padding(.horizontal, RFSpacing.md)
                    .padding(.vertical, RFSpacing.sm)
                }
                .onChange(of: viewModel.messages.count) {
                    scrollToBottom(proxy: proxy)
                }
                .onChange(of: viewModel.isTyping) {
                    if viewModel.isTyping {
                        scrollToBottom(proxy: proxy)
                    }
                }
            }
        }
    }

    private var loadMoreButton: some View {
        RFButton(
            String(localized: "chat.loadMore"),
            style: .ghost,
            size: .small
        ) {
            Task {
                await viewModel.loadMoreMessages()
            }
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }

    // MARK: - Chat Input

    private var chatInputView: some View {
        RFChatInput(
            text: $viewModel.messageText,
            isEnabled: !viewModel.isLoading,
            isSending: viewModel.isSending,
            isRecording: voiceInputViewModel.isRecording,
            audioLevel: voiceInputViewModel.audioLevel.normalizedLevel,
            onSend: {
                Task {
                    await viewModel.sendMessage()
                }
            },
            onMicTap: {
                handleMicTap()
            },
            onMicLongPress: {
                showVoiceConversation = true
            }
        )
    }

    // MARK: - Error Banner

    private func errorBanner(message: String) -> some View {
        VStack {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.white)
                RFText(message, style: .body, color: .white)
                Spacer()
                Button {
                    viewModel.dismissError()
                } label: {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white.opacity(0.8))
                }
            }
            .padding(RFSpacing.sm)
            .background(RFColors.error.opacity(0.9))
            .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))
            .rfElevation(.medium)
            .padding(.horizontal, RFSpacing.md)
            .padding(.top, RFSpacing.xs)

            Spacer()
        }
    }

    // MARK: - Voice

    private func setupVoiceCallbacks() {
        voiceInputViewModel.onTranscriptionComplete = { transcription in
            viewModel.messageText = transcription
            showVoiceOverlay = false
            Task {
                await viewModel.sendMessage()
            }
        }
    }

    private func handleMicTap() {
        if voiceInputViewModel.isRecording {
            // Kaydi durdur
            Task {
                await voiceInputViewModel.stopRecording()
            }
        } else if showVoiceOverlay {
            // Overlay acik ama kayit yok — kapat
            showVoiceOverlay = false
        } else {
            // Overlay ac ve kaydi baslat
            showVoiceOverlay = true
            Task {
                await voiceInputViewModel.startRecording()
            }
        }
    }

    // MARK: - WebSocket Handlers

    private func registerMessageHandlers() async {
        let vm = viewModel
        let voiceVm = voiceOutputViewModel

        // Text response handler (non-streaming fallback)
        let handler = ChatIncomingTextHandler { messageId, text in
            Task { @MainActor in
                vm.handleIncomingMessage(ChatMessage(
                    id: messageId,
                    content: text,
                    sender: .assistant,
                    type: .text
                ))
                // Otomatik sesli okuma (ayar aciksa)
                await voiceVm.autoPlayIfEnabled(text: text)
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.text.rawValue,
            handler: handler
        )

        // Streaming text delta handler
        let streamHandler = ChatStreamDeltaHandler { messageId, delta in
            Task { @MainActor in
                vm.handleStreamDelta(messageId: messageId, delta: delta)
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.chatStream.rawValue,
            handler: streamHandler
        )

        // Stream end handler
        let streamEndHandler = ChatStreamEndHandler { messageId, fullText in
            Task { @MainActor in
                vm.handleStreamEnd(messageId: messageId, fullText: fullText, type: .text)
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.chatStreamEnd.rawValue,
            handler: streamEndHandler
        )
    }

    // MARK: - Helpers

    private func scrollToBottom(proxy: ScrollViewProxy) {
        if viewModel.isTyping {
            withAnimation(RFAnimation.springGentle) {
                proxy.scrollTo("typing-indicator", anchor: .bottom)
            }
        } else if let lastMessage = viewModel.messages.last {
            withAnimation(RFAnimation.springGentle) {
                proxy.scrollTo(lastMessage.id, anchor: .bottom)
            }
        }
    }
}

#Preview {
    ChatView(
        viewModel: ChatViewModel(
            sendMessageUseCase: SendMessageUseCase(
                repository: PreviewChatRepository()
            ),
            loadHistoryUseCase: LoadChatHistoryUseCase(
                repository: PreviewChatRepository()
            )
        )
    )
}

/// Backend'den gelen text mesajlarini isler.
private final class ChatIncomingTextHandler: WebSocketMessageHandler {
    private let onTextReceived: @Sendable (String, String) -> Void

    init(onTextReceived: @escaping @Sendable (String, String) -> Void) {
        self.onTextReceived = onTextReceived
    }

    func handle(_ message: WebSocketBaseMessage) async {
        let text: String
        switch message.content {
        case .textResponse(let response):
            text = response.text
        case .text(let plainText):
            text = plainText
        default:
            return
        }
        onTextReceived(message.id, text)
    }
}

/// Streaming text delta mesajlarini isler.
private final class ChatStreamDeltaHandler: WebSocketMessageHandler {
    private let onDeltaReceived: @Sendable (String, String) -> Void

    init(onDeltaReceived: @escaping @Sendable (String, String) -> Void) {
        self.onDeltaReceived = onDeltaReceived
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .chatStream(let stream) = message.content else { return }
        onDeltaReceived(stream.messageId, stream.delta)
    }
}

/// Stream tamamlanma mesajlarini isler.
private final class ChatStreamEndHandler: WebSocketMessageHandler {
    private let onStreamEnd: @Sendable (String, String) -> Void

    init(onStreamEnd: @escaping @Sendable (String, String) -> Void) {
        self.onStreamEnd = onStreamEnd
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .chatStreamEnd(let content) = message.content else { return }
        onStreamEnd(content.messageId, content.fullText)
    }
}

/// Preview icin mock repository.
private final class PreviewChatRepository: ChatRepositoryProtocol, @unchecked Sendable {
    func sendMessage(text: String, sessionId: String) async throws -> ChatMessage {
        ChatMessage(content: text, sender: .user)
    }

    func loadHistory(
        sessionId: String,
        cursor: String?,
        limit: Int
    ) async throws -> ChatHistoryResult {
        ChatHistoryResult(
            messages: [
                ChatMessage(
                    content: "Merhaba! Size nasil yardimci olabilirim?",
                    sender: .assistant
                ),
                ChatMessage(
                    content: "Projemin durumunu kontrol eder misin?",
                    sender: .user
                ),
                ChatMessage(
                    content: "Projenizi kontrol ediyorum...",
                    sender: .assistant
                )
            ],
            hasMore: false,
            nextCursor: nil
        )
    }
}
