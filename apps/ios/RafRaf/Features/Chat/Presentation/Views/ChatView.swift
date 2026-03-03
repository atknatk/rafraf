import SwiftUI

/// Sohbet ekrani.
/// Kullanicinin AI asistan ile sesli ve metin tabanli iletisim kurdugu ana ekran.
/// LazyVStack ile performansli scroll, pagination, streaming ve typing indicator destegi.
struct ChatView: View {
    @State private var viewModel: ChatViewModel

    init(viewModel: ChatViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                messageListView
                chatInputView
            }
            .navigationTitle(String(localized: "chat.title"))
            .task {
                await viewModel.loadHistory()
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
            Spacer()
            RFLoadingView(message: String(localized: "chat.loading"))
            Spacer()
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
                            .transition(.move(edge: .bottom).combined(with: .opacity))
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
                    .foregroundStyle(RFColors.error)
                RFText(message, style: .body, color: .white)
                Spacer()
                RFButton(
                    String(localized: "chat.error.dismiss"),
                    style: .ghost,
                    size: .small
                ) {
                    viewModel.dismissError()
                }
            }
            .padding(RFSpacing.sm)
            .background(RFColors.error.opacity(0.9))
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .padding(.horizontal, RFSpacing.md)
            .padding(.top, RFSpacing.xs)

            Spacer()
        }
    }

    // MARK: - Helpers

    private func scrollToBottom(proxy: ScrollViewProxy) {
        if viewModel.isTyping {
            withAnimation(.easeOut(duration: 0.3)) {
                proxy.scrollTo("typing-indicator", anchor: .bottom)
            }
        } else if let lastMessage = viewModel.messages.last {
            withAnimation(.easeOut(duration: 0.3)) {
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
