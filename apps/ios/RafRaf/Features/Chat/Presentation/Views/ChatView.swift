import Factory
import SwiftUI

/// Sohbet ekrani — Claude-inspired sicak ve temiz gorunum.
/// Kullanicinin AI asistan ile sesli ve metin tabanli iletisim kurdugu ana ekran.
/// Proje bazli chat sessionlari destekler — her proje kendi mesaj gecmisine sahiptir.
struct ChatView: View {
    @State private var sessionManager: ChatSessionManager
    @State private var voiceInputViewModel = Container.shared.voiceInputViewModel()
    @State private var voiceOutputViewModel = Container.shared.voiceOutputViewModel()
    @State private var progressViewModel = Container.shared.progressViewModel()
    @State private var isProgressExpanded = false
    @State private var showSearch = false
    @State private var showVoiceOverlay = false
    @State private var showVoiceConversation = false
    @State private var quickCommandQuery: String = ""
    @State private var availableAgentProjects: [AgentProject] = []
    private let webSocketManager = Container.shared.webSocketConnectionManager()
    private let agentRepository: AgentRepositoryProtocol = Container.shared.agentRepository()

    /// Aktif ChatViewModel (session manager uzerinden).
    private var viewModel: ChatViewModel {
        sessionManager.activeViewModel
    }

    private var showCommandPalette: Bool {
        viewModel.messageText.hasPrefix("/") && !viewModel.messageText.contains(" ")
    }

    private var filteredCommands: [QuickCommand] {
        QuickCommands.filtered(by: viewModel.messageText)
    }

    init(sessionManager: ChatSessionManager) {
        self._sessionManager = State(initialValue: sessionManager)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                messageListView

                // Claude -p ilerleme gostergesi
                if progressViewModel.isVisible {
                    progressSection
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }

                // Ses kaydi overlay'i — chat input'un ustunde gosterilir
                if showVoiceOverlay {
                    RFVoiceInputView(viewModel: voiceInputViewModel)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                        .background(RFColors.fallbackSurface)
                }

                // Proaktif oneri chip'leri — input alaninin ustunde
                if !viewModel.pendingSuggestions.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: RFSpacing.xs) {
                            ForEach(viewModel.pendingSuggestions, id: \.self) { suggestion in
                                Button {
                                    sendSuggestion(suggestion)
                                    viewModel.pendingSuggestions = []
                                } label: {
                                    HStack(spacing: 4) {
                                        Image(systemName: "sparkles")
                                            .font(.system(size: 11))
                                        Text(suggestion)
                                            .font(.system(size: 13))
                                    }
                                    .padding(.horizontal, RFSpacing.sm)
                                    .padding(.vertical, RFSpacing.xs)
                                    .background(RFColors.fallbackPrimary.opacity(0.1))
                                    .foregroundStyle(RFColors.fallbackPrimary)
                                    .clipShape(Capsule())
                                }
                            }
                        }
                        .padding(.horizontal, RFSpacing.sm)
                    }
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }

                // Hizli komut paleti — "/" ile basladiginda goster
                if showCommandPalette && !filteredCommands.isEmpty {
                    RFQuickCommandPalette(commands: filteredCommands) { command in
                        viewModel.messageText = command.fullText
                        quickCommandQuery = ""
                    }
                    .padding(.horizontal, RFSpacing.sm)
                    .padding(.bottom, RFSpacing.xs)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }

                chatInputView
            }
            .background(RFColors.fallbackBackground)
            .navigationTitle(String(localized: "chat.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    RFProjectPicker(
                        activeProjectName: sessionManager.activeProjectName,
                        activeAgentId: sessionManager.activeAgentId,
                        agentProjects: availableAgentProjects,
                        onSelect: { agentId, projectId, projectName in
                            sessionManager.switchProject(id: projectId, name: projectName, agentId: agentId)
                        }
                    )
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showSearch = true
                    } label: {
                        Image(systemName: "magnifyingglass")
                            .accessibilityLabel(String(localized: "chat.search.title"))
                    }
                }
            }
            .sheet(isPresented: $showSearch) {
                ChatSearchView(projectId: viewModel.projectId)
            }
            .task {
                setupVoiceCallbacks()
                await registerMessageHandlers()
                await loadProjects()
                // History REST çağrısı, WebSocket bağlantısına bağlı değil
                await viewModel.loadHistory()
            }
            .onChange(of: webSocketManager.isConnected) { _, isConnected in
                if isConnected {
                    // Reconnect'te eksik mesajları getir; history boşsa tam yükle
                    if viewModel.messages.isEmpty {
                        Task { await viewModel.loadHistory() }
                    } else {
                        Task { await sessionManager.fetchMissedMessagesForAll() }
                    }
                    Task { await loadProjects() }
                }
            }
            .onChange(of: sessionManager.activeProjectId) {
                Task {
                    await viewModel.loadHistory()
                }
            }
            .onChange(of: progressViewModel.isActive) { _, isActive in
                if isActive {
                    withAnimation(RFAnimation.springResponsive) {
                        isProgressExpanded = true
                    }
                }
            }
            .overlay {
                if let errorMessage = viewModel.errorMessage {
                    errorBanner(message: errorMessage)
                }
            }
            .animation(RFAnimation.springResponsive, value: showVoiceOverlay)
            .animation(RFAnimation.springResponsive, value: progressViewModel.isVisible)
            .animation(RFAnimation.springResponsive, value: viewModel.pendingSuggestions.isEmpty)
            .animation(RFAnimation.springResponsive, value: showCommandPalette)
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
            text: Binding(
                get: { viewModel.messageText },
                set: { viewModel.messageText = $0 }
            ),
            isEnabled: !viewModel.isLoading,
            isSending: viewModel.isSending,
            isRecording: voiceInputViewModel.isRecording,
            audioLevel: voiceInputViewModel.audioLevel.normalizedLevel,
            onSend: {
                Task { @MainActor in
                    let projectName = sessionManager.activeProjectName ?? "RafRaf"
                    LiveActivityManager.shared.start(projectName: projectName)
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

    // MARK: - Progress Section

    private var progressSection: some View {
        VStack(spacing: 0) {
            // Compact header
            Button {
                withAnimation(RFAnimation.springResponsive) {
                    isProgressExpanded.toggle()
                }
            } label: {
                HStack(spacing: RFSpacing.xs) {
                    if progressViewModel.isActive {
                        ProgressView()
                            .controlSize(.mini)
                    } else {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(RFColors.success)
                            .font(.system(size: 14))
                    }

                    RFText(
                        progressViewModel.taskDescription,
                        style: .captionBold,
                        color: RFColors.fallbackTextPrimary
                    )
                    .lineLimit(1)

                    Spacer()

                    if progressViewModel.totalStepCount > 0 {
                        RFText(
                            "\(progressViewModel.completedStepCount)/\(progressViewModel.totalStepCount)",
                            style: .caption,
                            color: RFColors.fallbackTextTertiary
                        )
                    }

                    Image(systemName: isProgressExpanded ? "chevron.down" : "chevron.up")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(RFColors.fallbackTextTertiary)
                }
                .padding(.horizontal, RFSpacing.md)
                .padding(.vertical, RFSpacing.sm)
            }
            .buttonStyle(.plain)

            // Expandable timeline
            if isProgressExpanded, let state = progressViewModel.progressState {
                Divider()
                    .padding(.horizontal, RFSpacing.md)

                RFStepProgressView(
                    steps: state.steps,
                    currentStepIndex: state.currentStepIndex
                )
                .padding(.horizontal, RFSpacing.md)
                .padding(.vertical, RFSpacing.sm)
            }
        }
        .background(RFColors.fallbackSurface)
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

    // MARK: - Projects

    private func loadProjects() async {
        // Tum agent-proje iliskilerini DB'den tek sorguda getir (agent offline olsa bile)
        do {
            let projects = try await agentRepository.getAllAgentProjects()
            print("✅ loadProjects: \(projects.count) proje yuklendi")
            availableAgentProjects = projects
        } catch {
            print("❌ loadProjects hatasi: \(error)")
        }
    }

    // MARK: - Voice

    private func setupVoiceCallbacks() {
        voiceInputViewModel.onTranscriptionComplete = { transcription in
            viewModel.messageText = transcription
            showVoiceOverlay = false
            Task { @MainActor in
                let projectName = sessionManager.activeProjectName ?? "RafRaf"
                LiveActivityManager.shared.start(projectName: projectName)
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

    // MARK: - Suggestion

    /// Oneri chip'ine tıklandığında öneriyi mesaj olarak gönderir.
    private func sendSuggestion(_ text: String) {
        viewModel.messageText = text
        Task {
            await viewModel.sendMessage()
        }
    }

    // MARK: - WebSocket Handlers

    private func registerMessageHandlers() async {
        let voiceVm = voiceOutputViewModel
        let progressVm = progressViewModel

        // Text response handler (non-streaming fallback)
        let handler = ChatIncomingTextHandler { messageId, text in
            Task { @MainActor in
                sessionManager.activeViewModel.handleIncomingMessage(ChatMessage(
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
                sessionManager.activeViewModel.handleStreamDelta(messageId: messageId, delta: delta)
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.chatStream.rawValue,
            handler: streamHandler
        )

        // Stream end handler
        let streamEndHandler = ChatStreamEndHandler { messageId, fullText, tokensUsed, modelUsed in
            Task { @MainActor in
                sessionManager.activeViewModel.handleStreamEnd(
                    messageId: messageId,
                    fullText: fullText,
                    type: .text,
                    tokensUsed: tokensUsed,
                    modelUsed: modelUsed
                )
                progressVm.markCompleted()
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.chatStreamEnd.rawValue,
            handler: streamEndHandler
        )

        // Code diff handler
        let codeDiffHandler = ChatCodeDiffHandler { content in
            Task { @MainActor in
                let dto = CodeDiffPayloadDTO(
                    projectPath: content.projectPath,
                    totalAdditions: content.totalAdditions,
                    totalDeletions: content.totalDeletions,
                    filesChanged: content.filesChanged,
                    files: content.files.map { file in
                        CodeDiffFileDTO(
                            filePath: file.filePath,
                            isNewFile: file.isNewFile,
                            isDeleted: file.isDeleted,
                            additions: file.additions,
                            deletions: file.deletions,
                            lines: file.lines.map { line in
                                CodeDiffLineDTO(
                                    type: line.type,
                                    content: line.content,
                                    lineNumberOld: line.lineNumberOld,
                                    lineNumberNew: line.lineNumberNew
                                )
                            }
                        )
                    }
                )
                sessionManager.activeViewModel.handleCodeDiff(dto)
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.codeDiff.rawValue,
            handler: codeDiffHandler
        )

        // Progress handler
        let progressHandler = ChatProgressHandler { content in
            Task { @MainActor in
                let dto = ProgressEventDTO(
                    task: content.task,
                    step: content.step,
                    totalSteps: content.totalSteps,
                    percentage: content.percentage,
                    details: content.details,
                    phase: content.phase,
                    stepsDetail: content.stepsDetail?.map { step in
                        ProgressStepDTO(
                            id: step.id,
                            stepType: step.stepType,
                            label: step.label,
                            status: step.status,
                            toolName: step.toolName,
                            durationSeconds: step.durationSeconds,
                            detail: step.detail
                        )
                    }
                )
                let state = ProgressMapper.toDomain(from: dto)
                progressVm.updateProgress(state)
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.progress.rawValue,
            handler: progressHandler
        )

        // Suggestion handler
        let suggestionHandler = ChatSuggestionHandler { messageId, suggestions in
            Task { @MainActor in
                sessionManager.activeViewModel.handleSuggestions(
                    messageId: messageId, suggestions: suggestions
                )
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.suggestion.rawValue,
            handler: suggestionHandler
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
        sessionManager: ChatSessionManager(
            sendMessageUseCaseFactory: {
                SendMessageUseCase(repository: PreviewChatRepository())
            },
            loadHistoryUseCaseFactory: {
                LoadChatHistoryUseCase(repository: PreviewChatRepository())
            },
            fetchMissedMessagesUseCaseFactory: {
                FetchMissedMessagesUseCase(repository: PreviewChatRepository())
            }
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
    private let onStreamEnd: @Sendable (String, String, Int?, String?) -> Void

    init(onStreamEnd: @escaping @Sendable (String, String, Int?, String?) -> Void) {
        self.onStreamEnd = onStreamEnd
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .chatStreamEnd(let content) = message.content else { return }
        let totalTokens: Int?
        if let usage = content.tokensUsed {
            let sum = usage.input + usage.output
            totalTokens = sum > 0 ? sum : nil
        } else {
            totalTokens = nil
        }
        let model: String? = content.modelUsed.isEmpty ? nil : content.modelUsed
        onStreamEnd(content.messageId, content.fullText, totalTokens, model)
    }
}

/// Code diff mesajlarini isler.
private final class ChatCodeDiffHandler: WebSocketMessageHandler {
    private let onDiffReceived: @Sendable (CodeDiffContent) -> Void

    init(onDiffReceived: @escaping @Sendable (CodeDiffContent) -> Void) {
        self.onDiffReceived = onDiffReceived
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .codeDiff(let content) = message.content else { return }
        onDiffReceived(content)
    }
}

/// Progress mesajlarini isler.
private final class ChatProgressHandler: WebSocketMessageHandler {
    private let onProgressReceived: @Sendable (ProgressMessageContent) -> Void

    init(onProgressReceived: @escaping @Sendable (ProgressMessageContent) -> Void) {
        self.onProgressReceived = onProgressReceived
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .progress(let content) = message.content else { return }
        onProgressReceived(content)
    }
}

/// Proaktif oneri mesajlarini isler.
private final class ChatSuggestionHandler: WebSocketMessageHandler {
    private let onSuggestionReceived: @Sendable (String, [String]) -> Void

    init(onSuggestionReceived: @escaping @Sendable (String, [String]) -> Void) {
        self.onSuggestionReceived = onSuggestionReceived
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .suggestion(let content) = message.content else { return }
        onSuggestionReceived(content.messageId, content.suggestions)
    }
}

/// Preview icin mock repository.
private final class PreviewChatRepository: ChatRepositoryProtocol, @unchecked Sendable {
    func sendMessage(text: String, sessionId: String, projectId: String? = nil, agentId: String? = nil) async throws -> ChatMessage {
        ChatMessage(content: text, sender: .user)
    }

    func loadHistory(
        sessionId: String,
        projectId: String? = nil,
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

    func fetchMissedMessages(
        since: String,
        sessionId: String?,
        projectId: String?
    ) async throws -> [ChatMessage] {
        []
    }
}
