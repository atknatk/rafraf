import Factory
import SwiftUI

/// Sohbet ekrani — Claude-inspired sicak ve temiz gorunum.
/// Kullanicinin AI asistan ile sesli ve metin tabanli iletisim kurdugu ana ekran.
struct ChatView: View {
    @State private var viewModel: ChatViewModel
    private let webSocketManager = Container.shared.webSocketConnectionManager()

    init(viewModel: ChatViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                messageListView
                chatInputView
            }
            .background(RFColors.fallbackBackground)
            .navigationTitle(String(localized: "chat.title"))
            .navigationBarTitleDisplayMode(.inline)
            .task {
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
                                onCopy: { viewModel.copyMessage($0) }
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
            isSending: viewModel.isSending
        ) {
            Task {
                await viewModel.sendMessage()
            }
        }
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

    // MARK: - WebSocket Handlers

    private func registerMessageHandlers() async {
        let vm = viewModel
        let handler = ChatIncomingTextHandler { messageId, text in
            Task { @MainActor in
                vm.handleIncomingMessage(ChatMessage(
                    id: messageId,
                    content: text,
                    sender: .assistant,
                    type: .text
                ))
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.text.rawValue,
            handler: handler
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
