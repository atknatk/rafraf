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
    @State private var bookmarkService = BookmarkService()
    @State private var showBookmarks = false
    @State private var showSearch = false
    @State private var showVoiceOverlay = false
    @State private var showVoiceConversation = false
    @State private var quickCommandQuery: String = ""
    @State private var availableAgentProjects: [AgentProject] = []
    @State private var exportedText: String?
    @State private var showExport = false
    @State private var connectionMonitor = ConnectionQualityMonitor()
    @State private var githubEventService = GitHubEventService()
    @State private var showGitHubBanner = false
    @State private var latestAgentStatusChange: AgentStatusChangePayload?
    @State private var latestTaskStatusContent: TaskStatusContent?
    @State private var isAtBottom = true
    @State private var unreadCount = 0
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
                // Bekleyen kuyruklanmis mesaj banner'i
                if !viewModel.messageQueue.isEmpty {
                    queueBannerView
                        .transition(.move(edge: .top).combined(with: .opacity))
                }

                // GitHub webhook event banner
                if let event = githubEventService.latestEvent {
                    githubEventBanner(event)
                        .transition(.move(edge: .top).combined(with: .opacity))
                }

                // Agent status change banner
                if let change = latestAgentStatusChange {
                    agentStatusBanner(change)
                        .transition(.move(edge: .top).combined(with: .opacity))
                }

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

                suggestionChipsView
                commandPaletteView

                chatInputView
            }
            .background(RFColors.fallbackBackground)
            .navigationTitle(String(localized: "chat.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    RFConnectionIndicator(
                        quality: connectionMonitor.quality,
                        latencyMs: connectionMonitor.latencyMs
                    )
                }
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
                    Menu {
                        Button {
                            showSearch = true
                        } label: {
                            Label(String(localized: "chat.search.title"), systemImage: "magnifyingglass")
                        }
                        Button {
                            showBookmarks = true
                        } label: {
                            Label(String(localized: "bookmarks.title"), systemImage: "bookmark")
                        }
                        Button {
                            Task { await exportConversation() }
                        } label: {
                            Label(String(localized: "chat.export.title"), systemImage: "square.and.arrow.up")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
            .sheet(isPresented: $showSearch) {
                ChatSearchView(projectId: viewModel.projectId)
            }
            .sheet(isPresented: $showBookmarks) {
                BookmarksView(bookmarkService: bookmarkService)
            }
            .sheet(isPresented: $showExport) {
                if let text = exportedText {
                    ShareSheet(items: [text])
                }
            }
            .task {
                setupVoiceCallbacks()
                setupConnectionMonitor()
                await registerMessageHandlers()
                await loadProjects()
                // History REST çağrısı, WebSocket bağlantısına bağlı değil
                await viewModel.loadHistory()
            }
            .onChange(of: webSocketManager.isConnected) { _, isConnected in
                if isConnected {
                    connectionMonitor.connectionEstablished()
                    // Reconnect'te eksik mesajları getir; history boşsa tam yükle
                    if viewModel.messages.isEmpty {
                        Task { await viewModel.loadHistory() }
                    } else {
                        Task { await sessionManager.fetchMissedMessagesForAll() }
                    }
                    Task { await loadProjects() }
                    // Kuyruklanmis mesajlari gonder
                    Task { await viewModel.flushQueue() }
                } else {
                    connectionMonitor.connectionLost()
                }
            }
            .onChange(of: viewModel.messageText) {
                // Kullanici yazmaya basladiginda onerileri temizle
                if !viewModel.messageText.isEmpty && !viewModel.pendingSuggestions.isEmpty {
                    withAnimation(RFAnimation.springResponsive) {
                        viewModel.pendingSuggestions = []
                    }
                }
            }
            .onChange(of: sessionManager.activeProjectId) {
                // Proje degistiyse sadece mesaj gecmisi bossa yukle
                // (geri geldigimizde mevcut mesajlar korunur)
                Task {
                    if viewModel.messages.isEmpty {
                        await viewModel.loadHistory()
                    }
                }
            }
            .onChange(of: progressViewModel.isActive) { _, isActive in
                if isActive {
                    withAnimation(RFAnimation.springResponsive) {
                        isProgressExpanded = true
                    }
                }
            }
            .onChange(of: latestTaskStatusContent?.taskId) {
                // Yeni task geldiginde Live Activity baslat
                guard let content = latestTaskStatusContent else { return }
                let projectName = sessionManager.activeProjectName ?? "RafRaf"
                Task {
                    await LiveActivityManager.shared.startTask(
                        taskId: content.taskId,
                        taskTitle: content.detail ?? content.currentStep ?? "AI Task",
                        projectName: projectName
                    )
                }
            }
            .onChange(of: latestTaskStatusContent?.progressPct) {
                // Task progress guncellemesi
                guard let content = latestTaskStatusContent else { return }
                let isTerminal = ["completed", "failed", "cancelled"].contains(content.status)
                if isTerminal {
                    Task { await LiveActivityManager.shared.endTask() }
                } else {
                    Task {
                        await LiveActivityManager.shared.updateTask(
                            status: content.status,
                            currentStep: content.currentStep ?? content.status,
                            progress: Double(content.progressPct) / 100.0,
                            completedSteps: content.completedSteps,
                            totalSteps: content.totalSteps,
                            phaseIcon: stepIcon(for: content.currentStep),
                            estimatedSeconds: nil
                        )
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
            .animation(RFAnimation.springResponsive, value: viewModel.messageQueue.isEmpty)
            .animation(RFAnimation.springResponsive, value: githubEventService.latestEvent?.event)
            .animation(RFAnimation.springResponsive, value: latestAgentStatusChange?.hostId)
            .fullScreenCover(isPresented: $showVoiceConversation) {
                let voiceVM = Container.shared.voiceConversationViewModel()
                VoiceConversationView(viewModel: voiceVM) {
                    showVoiceConversation = false
                }
                .task {
                    await voiceVM.enterVoiceMode()
                }
            }
            .background {
                keyboardShortcutsLayer
            }
        }
    }

    // MARK: - Keyboard Shortcuts

    /// Hardware klavye kisayollari icin gorunmez buton katmani.
    @ViewBuilder
    private var keyboardShortcutsLayer: some View {
        Group {
            // Cmd+K: Komut paleti ac (ilk "/" yazdır)
            Button("") {
                if viewModel.messageText.isEmpty {
                    viewModel.messageText = "/"
                }
            }
            .keyboardShortcut("k", modifiers: .command)
            .hidden()

            // Cmd+F: Arama
            Button("") {
                showSearch = true
            }
            .keyboardShortcut("f", modifiers: .command)
            .hidden()

            // Escape: Odak kaldir / overlay kapat
            Button("") {
                viewModel.messageText = ""
            }
            .keyboardShortcut(.escape, modifiers: [])
            .hidden()
        }
    }

    // MARK: - Message List

    @ViewBuilder
    private var messageListView: some View {
        if viewModel.isLoading {
            ChatSkeletonView()
        } else if viewModel.messages.isEmpty {
            welcomeView
        } else {
            ZStack(alignment: .bottomTrailing) {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: RFSpacing.sm) {
                            // Ust bosluk — icerik azken mesajlari asagiya iter
                            Spacer(minLength: 0)
                                .frame(maxHeight: .infinity)
                            if viewModel.hasMoreMessages {
                                loadMoreButton
                            }

                            ForEach(viewModel.messages) { message in
                                // Tarih ayirici — onceki mesajla gun farki varsa goster
                                if shouldShowDateSeparator(for: message) {
                                    chatDateSeparator(for: message.timestamp)
                                }

                                RFMessageBubble(
                                    message: message,
                                    onCopy: { viewModel.copyMessage($0) },
                                    onSpeak: message.sender == .assistant
                                        ? { Task { await voiceOutputViewModel.speak(text: message.content) } }
                                        : nil,
                                    onBookmark: message.sender == .assistant ? {
                                        bookmarkService.bookmark(
                                            message,
                                            projectId: viewModel.projectId,
                                            projectName: sessionManager.activeProjectName
                                        )
                                    } : nil,
                                    onRating: message.sender == .assistant ? { [message] rating in
                                        let msgId = message.id
                                        Task<Void, Never> { await viewModel.rateMessage(id: msgId, rating: rating) }
                                    } : nil
                                )
                                .id(message.id)
                                .transition(RFTransition.chatMessage)
                            }

                            // Inline tool aktivite karti — Claude Code tarzi
                            if let activity = viewModel.currentActivity, !activity.isCompleted {
                                RFToolActivityCard(activity: activity)
                                    .id("tool-activity")
                                    .transition(.move(edge: .bottom).combined(with: .opacity))
                            }

                            if viewModel.isTyping && viewModel.currentActivity == nil {
                                RFTypingIndicator()
                                    .id("typing-indicator")
                            }

                            // Bottom sentinel — tracks scroll position
                            Color.clear
                                .frame(height: 1)
                                .id("scroll-bottom")
                                .onAppear {
                                    withAnimation(RFAnimation.springResponsive) {
                                        isAtBottom = true
                                        unreadCount = 0
                                    }
                                }
                                .onDisappear {
                                    withAnimation(RFAnimation.springResponsive) {
                                        isAtBottom = false
                                    }
                                }
                        }
                        .padding(.horizontal, RFSpacing.md)
                        .padding(.vertical, RFSpacing.sm)
                    }
                    .defaultScrollAnchor(.bottom)
                    .scrollDismissesKeyboard(.interactively)
                    .refreshable {
                        await viewModel.loadHistory()
                        isAtBottom = true
                        unreadCount = 0
                    }
                    .onChange(of: viewModel.messages.count) {
                        if isAtBottom {
                            scrollToBottom(proxy: proxy)
                        } else {
                            unreadCount += 1
                        }
                    }
                    .onChange(of: viewModel.isTyping) {
                        if viewModel.isTyping && isAtBottom {
                            scrollToBottom(proxy: proxy)
                        }
                    }
                    .onChange(of: viewModel.messages.last?.content) {
                        // Streaming icerik buyurken en alta kaydır
                        if isAtBottom, let last = viewModel.messages.last, last.isStreaming {
                            scrollToBottom(proxy: proxy)
                        }
                    }
                    .overlay(alignment: .bottomTrailing) {
                        if !isAtBottom {
                            scrollToBottomFAB(proxy: proxy)
                                .padding(.trailing, RFSpacing.md)
                                .padding(.bottom, RFSpacing.sm)
                                .transition(.scale.combined(with: .opacity))
                        }
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

    private func scrollToBottomFAB(proxy: ScrollViewProxy) -> some View {
        Button {
            withAnimation(RFAnimation.springResponsive) {
                scrollToBottom(proxy: proxy)
                unreadCount = 0
            }
        } label: {
            ZStack(alignment: .topTrailing) {
                Circle()
                    .fill(RFColors.fallbackSurface)
                    .frame(width: 40, height: 40)
                    .shadow(color: .black.opacity(0.15), radius: 4, x: 0, y: 2)
                    .overlay {
                        Image(systemName: "chevron.down")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundStyle(RFColors.fallbackTextPrimary)
                    }

                if unreadCount > 0 {
                    Text(unreadCount > 99 ? "99+" : "\(unreadCount)")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(RFColors.fallbackPrimary)
                        .clipShape(Capsule())
                        .offset(x: 6, y: -6)
                }
            }
        }
        .buttonStyle(RFPressButtonStyle())
        .animation(RFAnimation.springResponsive, value: unreadCount)
    }

    // MARK: - Suggestion Chips + Command Palette

    @ViewBuilder
    private var suggestionChipsView: some View {
        if !viewModel.pendingSuggestions.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: RFSpacing.xs) {
                    ForEach(Array(viewModel.pendingSuggestions.enumerated()), id: \.element) { index, suggestion in
                        Button {
                            sendSuggestion(suggestion)
                            viewModel.pendingSuggestions = []
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: "sparkles")
                                    .font(.system(size: 11))
                                Text(suggestion)
                                    .font(.system(size: 13))
                                    .lineLimit(1)
                            }
                            .padding(.horizontal, RFSpacing.sm)
                            .padding(.vertical, RFSpacing.xs)
                            .background(RFColors.fallbackPrimary.opacity(0.1))
                            .foregroundStyle(RFColors.fallbackPrimary)
                            .clipShape(Capsule())
                            .overlay(
                                Capsule()
                                    .stroke(RFColors.fallbackPrimary.opacity(0.2), lineWidth: 0.5)
                            )
                        }
                        .transition(.scale.combined(with: .opacity))
                        .animation(
                            RFAnimation.springResponsive.delay(Double(index) * 0.05),
                            value: viewModel.pendingSuggestions.count
                        )
                    }
                }
                .padding(.horizontal, RFSpacing.sm)
                .padding(.vertical, RFSpacing.xxs)
            }
            .transition(.move(edge: .bottom).combined(with: .opacity))
        }
    }

    @ViewBuilder
    private var commandPaletteView: some View {
        if showCommandPalette && !filteredCommands.isEmpty {
            RFQuickCommandPalette(commands: filteredCommands) { command in
                viewModel.messageText = command.fullText
                quickCommandQuery = ""
                HapticManager.commandPaletteOpened()
            }
            .padding(.horizontal, RFSpacing.sm)
            .padding(.bottom, RFSpacing.xs)
            .transition(.move(edge: .bottom).combined(with: .opacity))
        }
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
            isProcessing: viewModel.isTyping || viewModel.currentActivity?.isActive == true,
            isRecording: voiceInputViewModel.isRecording,
            audioLevel: voiceInputViewModel.audioLevel.normalizedLevel,
            onSend: {
                Task { @MainActor in
                    let text = viewModel.messageText.trimmingCharacters(in: .whitespacesAndNewlines)
                    // /export komutu yerel olarak islenir
                    if text == "/export" {
                        viewModel.messageText = ""
                        Task { await exportConversation() }
                        return
                    }
                    let projectName = sessionManager.activeProjectName ?? "RafRaf"
                    let connected = webSocketManager.isConnected
                    if connected {
                        LiveActivityManager.shared.start(projectName: projectName)
                    }
                    await viewModel.sendMessage(isConnected: connected)
                }
            },
            onStop: {
                Task { @MainActor in
                    let msg = WebSocketMessageFactory.cancelStreamMessage()
                    try? await webSocketManager.sendMessage(msg)
                    viewModel.handleTypingIndicator(isTyping: false)
                    HapticManager.error()
                    LiveActivityManager.shared.end()
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

    // MARK: - Welcome View

    private var welcomeView: some View {
        ScrollView {
            VStack(spacing: RFSpacing.xl) {
                Spacer(minLength: RFSpacing.xxxl)

                // Logo & baslik
                VStack(spacing: RFSpacing.sm) {
                    Image(systemName: "sparkles")
                        .font(.system(size: 36, weight: .light))
                        .foregroundStyle(RFColors.fallbackPrimary)

                    RFText(
                        String(localized: "chat.welcome.title"),
                        style: .title,
                        color: RFColors.fallbackTextPrimary
                    )

                    RFText(
                        String(localized: "chat.welcome.subtitle"),
                        style: .body,
                        color: RFColors.fallbackTextSecondary
                    )
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, RFSpacing.xl)
                }

                // Starter prompt kartlari
                LazyVGrid(columns: [
                    GridItem(.flexible(), spacing: RFSpacing.sm),
                    GridItem(.flexible(), spacing: RFSpacing.sm)
                ], spacing: RFSpacing.sm) {
                    ForEach(starterPrompts, id: \.text) { prompt in
                        Button {
                            viewModel.messageText = prompt.text
                            Task {
                                await viewModel.sendMessage(isConnected: webSocketManager.isConnected)
                            }
                        } label: {
                            VStack(alignment: .leading, spacing: RFSpacing.xs) {
                                Image(systemName: prompt.icon)
                                    .font(.system(size: 18))
                                    .foregroundStyle(RFColors.fallbackPrimary)
                                RFText(prompt.label, style: .captionBold, color: RFColors.fallbackTextPrimary)
                                RFText(prompt.description, style: .caption, color: RFColors.fallbackTextSecondary)
                                    .lineLimit(2)
                            }
                            .padding(RFSpacing.sm)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(RFColors.fallbackSurface)
                            .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))
                            .overlay(
                                RoundedRectangle(cornerRadius: RFCornerRadius.medium)
                                    .stroke(RFColors.divider.opacity(0.5), lineWidth: 0.5)
                            )
                        }
                        .buttonStyle(RFPressButtonStyle())
                    }
                }
                .padding(.horizontal, RFSpacing.md)

                Spacer(minLength: RFSpacing.xl)
            }
        }
        .scrollDismissesKeyboard(.interactively)
    }

    /// Starter prompt verileri.
    private var starterPrompts: [(icon: String, label: String, description: String, text: String)] {
        [
            (
                icon: "chart.bar.xaxis",
                label: String(localized: "chat.starter.status.label"),
                description: String(localized: "chat.starter.status.desc"),
                text: String(localized: "chat.starter.status.prompt")
            ),
            (
                icon: "hammer.fill",
                label: String(localized: "chat.starter.build.label"),
                description: String(localized: "chat.starter.build.desc"),
                text: String(localized: "chat.starter.build.prompt")
            ),
            (
                icon: "testtube.2",
                label: String(localized: "chat.starter.test.label"),
                description: String(localized: "chat.starter.test.desc"),
                text: String(localized: "chat.starter.test.prompt")
            ),
            (
                icon: "arrow.triangle.pull",
                label: String(localized: "chat.starter.pr.label"),
                description: String(localized: "chat.starter.pr.desc"),
                text: String(localized: "chat.starter.pr.prompt")
            )
        ]
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

    // MARK: - Queue Banner

    private var queueBannerView: some View {
        HStack(spacing: RFSpacing.xs) {
            Image(systemName: "clock.arrow.circlepath")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(.white)
            RFText(
                String(format: String(localized: "chat.queue.banner"), viewModel.messageQueue.count),
                style: .captionBold,
                color: .white
            )
            Spacer()
        }
        .padding(.horizontal, RFSpacing.md)
        .padding(.vertical, RFSpacing.xs)
        .background(RFColors.fallbackPrimary)
    }

    // MARK: - GitHub Event Banner

    private func githubEventBanner(_ event: GitHubEventPayload) -> some View {
        HStack(spacing: RFSpacing.xs) {
            Image(systemName: githubEventIcon(event.event))
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(.white)
            VStack(alignment: .leading, spacing: 2) {
                RFText(
                    githubEventTitle(event),
                    style: .captionBold,
                    color: .white
                )
                RFText(
                    event.repo,
                    style: .caption,
                    color: .white.opacity(0.8)
                )
            }
            Spacer()
            Button {
                withAnimation(RFAnimation.springResponsive) {
                    githubEventService.clearLatest()
                }
            } label: {
                Image(systemName: "xmark")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white.opacity(0.8))
            }
        }
        .padding(.horizontal, RFSpacing.md)
        .padding(.vertical, RFSpacing.xs)
        .background(Color(red: 0.1, green: 0.1, blue: 0.1).opacity(0.92))
        .onTapGesture {
            // Future: open GitHub URL
        }
        .task {
            try? await Task.sleep(nanoseconds: 5_000_000_000)
            withAnimation(RFAnimation.springResponsive) {
                githubEventService.clearLatest()
            }
        }
    }

    private func githubEventIcon(_ event: String) -> String {
        switch event {
        case "push": return "arrow.up.circle.fill"
        case "pull_request": return "arrow.triangle.pull"
        case "issues": return "exclamationmark.circle.fill"
        default: return "bell.fill"
        }
    }

    private func githubEventTitle(_ event: GitHubEventPayload) -> String {
        switch event.event {
        case "push":
            let commits = event.summary.commitCount ?? 0
            return "\(event.summary.pusher ?? "Someone") pushed \(commits) commit\(commits == 1 ? "" : "s") to \(event.summary.branch ?? "main")"
        case "pull_request":
            let action = event.action == "merged" ? "merged" : event.action
            let title = event.summary.title ?? "PR"
            return "PR \(action): \(title)"
        case "issues":
            let title = event.summary.title ?? "Issue"
            return "Issue \(event.action): \(title)"
        default:
            return "\(event.event) \(event.action)"
        }
    }

    // MARK: - Date Separator

    private func chatDateSeparator(for date: Date) -> some View {
        HStack(spacing: RFSpacing.xs) {
            Rectangle()
                .fill(RFColors.fallbackTextTertiary.opacity(0.3))
                .frame(height: 0.5)
            RFText(formattedSeparatorDate(date), style: .caption, color: RFColors.fallbackTextTertiary)
                .fixedSize()
            Rectangle()
                .fill(RFColors.fallbackTextTertiary.opacity(0.3))
                .frame(height: 0.5)
        }
        .padding(.vertical, RFSpacing.xs)
    }

    private func formattedSeparatorDate(_ date: Date) -> String {
        if Calendar.current.isDateInToday(date) {
            return String(localized: "chat.date.today")
        } else if Calendar.current.isDateInYesterday(date) {
            return String(localized: "chat.date.yesterday")
        } else {
            let formatter = DateFormatter()
            let isThisYear = Calendar.current.isDate(date, equalTo: Date(), toGranularity: .year)
            formatter.dateFormat = isThisYear ? "d MMMM" : "d MMMM yyyy"
            return formatter.string(from: date)
        }
    }

    // MARK: - Agent Status Banner

    private func agentStatusBanner(_ change: AgentStatusChangePayload) -> some View {
        let isOnline = change.status == "online"
        let color: Color = isOnline ? RFColors.success : RFColors.fallbackTextTertiary
        let icon = isOnline ? "desktopcomputer" : "desktopcomputer.trianglebadge.exclamationmark"
        let title = isOnline
            ? (change.isNew == true
                ? String(format: String(localized: "agent.status.newOnline"), change.hostId)
                : String(format: String(localized: "agent.status.backOnline"), change.hostId))
            : String(format: String(localized: "agent.status.wentOffline"), change.hostId)

        return HStack(spacing: RFSpacing.xs) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(color)
            RFText(title, style: .captionBold, color: RFColors.fallbackTextPrimary)
            Spacer()
            Button {
                withAnimation(RFAnimation.springResponsive) {
                    latestAgentStatusChange = nil
                }
            } label: {
                Image(systemName: "xmark")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(RFColors.fallbackTextTertiary)
            }
        }
        .padding(.horizontal, RFSpacing.md)
        .padding(.vertical, RFSpacing.xs)
        .background(RFColors.fallbackSurface)
        .overlay(alignment: .bottom) {
            Divider()
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

    // MARK: - Export

    private func stepIcon(for step: String?) -> String {
        switch step {
        case "architect": return "doc.text.magnifyingglass"
        case "developer": return "hammer.fill"
        case "tester": return "checkmark.shield.fill"
        case "reviewer": return "eye.fill"
        default: return "circle"
        }
    }

    private func exportConversation() async {
        var lines: [String] = [String(localized: "chat.export.header"), ""]
        for msg in viewModel.messages {
            let role = msg.sender == .user ? "**\(String(localized: "chat.export.role.user"))**" : "**\(String(localized: "chat.export.role.assistant"))**"
            lines.append("### \(role)")
            lines.append(msg.content)
            lines.append("")
        }
        exportedText = lines.joined(separator: "\n")
        showExport = true
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

    // MARK: - Connection Monitor

    private func setupConnectionMonitor() {
        webSocketManager.onPingSent = { [weak connectionMonitor] in
            Task { @MainActor in
                connectionMonitor?.recordPingSent()
            }
        }
        // Mevcut baglanti durumunu yansit
        if webSocketManager.isConnected {
            connectionMonitor.connectionEstablished()
        }
    }

    // MARK: - Voice

    private func setupVoiceCallbacks() {
        voiceInputViewModel.onTranscriptionComplete = { transcription in
            viewModel.messageText = transcription
            showVoiceOverlay = false
            Task { @MainActor in
                let connected = webSocketManager.isConnected
                let projectName = sessionManager.activeProjectName ?? "RafRaf"
                if connected {
                    LiveActivityManager.shared.start(projectName: projectName)
                }
                await viewModel.sendMessage(isConnected: connected)
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
            await viewModel.sendMessage(isConnected: webSocketManager.isConnected)
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

        let chatVm = sessionManager.activeViewModel

        // Progress handler — hem ProgressVM hem de ChatViewModel'e yonlendir
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
                // Inline tool aktivite kartini guncelle
                chatVm.handleProgress(content)
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

        // Pong handler — baglanti gecikme olcumu icin
        let pongHandler = ChatPongHandler {
            Task { @MainActor in
                connectionMonitor.recordPongReceived()
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.pong.rawValue,
            handler: pongHandler
        )

        // GitHub webhook event handler — real-time GitHub activity
        let eventService = githubEventService
        let githubHandler = GitHubEventHandler(service: eventService)
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.githubEvent.rawValue,
            handler: githubHandler
        )

        // Typing indicators — show/hide RFTypingIndicator
        let typingStartHandler = GenericNoPayloadHandler {
            Task { @MainActor in
                sessionManager.activeViewModel.handleTypingIndicator(isTyping: true)
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.typingStart.rawValue,
            handler: typingStartHandler
        )
        let typingEndHandler = GenericNoPayloadHandler {
            Task { @MainActor in
                sessionManager.activeViewModel.handleTypingIndicator(isTyping: false)
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.typingEnd.rawValue,
            handler: typingEndHandler
        )

        // Stream cancelled ack — iptal onayı gelince UI temizle
        let streamCancelledHandler = GenericNoPayloadHandler {
            Task { @MainActor in
                sessionManager.activeViewModel.handleTypingIndicator(isTyping: false)
                progressVm.markCompleted()
                LiveActivityManager.shared.end()
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.streamCancelled.rawValue,
            handler: streamCancelledHandler
        )

        // Agent status change handler — proactive online/offline notifications
        let agentStatusHandler = AgentStatusChangeHandler { payload in
            Task { @MainActor in
                withAnimation(RFAnimation.springResponsive) {
                    self.latestAgentStatusChange = payload
                }
                // Auto-dismiss after 4s
                try? await Task.sleep(nanoseconds: 4_000_000_000)
                withAnimation(RFAnimation.springResponsive) {
                    self.latestAgentStatusChange = nil
                }
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.agentStatusChange.rawValue,
            handler: agentStatusHandler
        )

        // Task status handler — task_status mesajlarini isler
        let taskStatusHandler = TaskStatusHandler { content in
            Task { @MainActor in
                self.latestTaskStatusContent = content
            }
        }
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.taskStatus.rawValue,
            handler: taskStatusHandler
        )
    }

    // MARK: - Helpers

    /// Mesajin ustunde tarih ayirici gosterilip gosterilmeyecegini belirler.
    private func shouldShowDateSeparator(for message: ChatMessage) -> Bool {
        guard let index = viewModel.messages.firstIndex(where: { $0.id == message.id }) else {
            return false
        }
        if index == 0 { return true }
        return !Calendar.current.isDate(
            viewModel.messages[index - 1].timestamp,
            inSameDayAs: message.timestamp
        )
    }

    private func scrollToBottom(proxy: ScrollViewProxy) {
        withAnimation(RFAnimation.springGentle) {
            proxy.scrollTo("scroll-bottom", anchor: .bottom)
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

/// Pong mesajlarini isler — baglanti gecikme olcumu icin.
private final class ChatPongHandler: WebSocketMessageHandler {
    private let onPong: @Sendable () -> Void

    init(onPong: @escaping @Sendable () -> Void) {
        self.onPong = onPong
    }

    func handle(_ message: WebSocketBaseMessage) async {
        onPong()
    }
}

/// Agent durum degisikligi mesajlarini isler.
private final class AgentStatusChangeHandler: WebSocketMessageHandler {
    private let onStatusChange: @Sendable (AgentStatusChangePayload) -> Void

    init(onStatusChange: @escaping @Sendable (AgentStatusChangePayload) -> Void) {
        self.onStatusChange = onStatusChange
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .agentStatusChange(let payload) = message.content else { return }
        onStatusChange(payload)
    }
}

/// Payload icermeyen mesajlari (typing.start, typing.end) isler.
private final class GenericNoPayloadHandler: WebSocketMessageHandler {
    private let onReceived: @Sendable () -> Void

    init(onReceived: @escaping @Sendable () -> Void) {
        self.onReceived = onReceived
    }

    func handle(_ message: WebSocketBaseMessage) async {
        onReceived()
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

    func rateMessage(id: String, rating: MessageRating) async throws {
        // Preview no-op
    }
}
