import SwiftUI

/// Spike #5 fallback agacina uygun, modal formatli bir onay sheet'i.
///
/// Doc 10 §8 — T3.1 Approval sheet UX kabul kriteri:
///   - write/edit/bash/WebFetch/WebSearch -> sheet ile sor (3 buton).
///   - read/grep/ls -> auto-allow (UI hic gosterilmez, coordinator karar verir).
///   - 30s auto-deny (kullanici cevap vermezse).
///   - Allow once / Allow always (session) / Deny butonlari + risk badge +
///     haptic feedback.
///
/// Bu view klasik `RFApprovalCard`'dan ayri; yeni tool-call onay akisi icin
/// kullanilir. Iki view tum tap noktalarini ayri tutar — eski akislar
/// regression yasamaz.
struct RFApprovalSheet: View {
    let request: ApprovalSheetRequest
    let onDecision: (ApprovalUserChoice) -> Void

    /// Auto-deny zamanlayici icin kalan saniye.
    @State private var remainingSeconds: Int
    @State private var timerTask: Task<Void, Never>?
    @State private var isPromptExpanded: Bool = false
    @State private var isDecided: Bool = false

    /// Test gorunurlugu icin haptic on/off.
    private let hapticsEnabled: Bool

    /// Test gorunurlugu icin auto-timer on/off.
    private let timerEnabled: Bool

    /// Prompt onizleme limit'i (truncate).
    private static let inputPreviewLimit = 240

    init(
        request: ApprovalSheetRequest,
        hapticsEnabled: Bool = true,
        timerEnabled: Bool = true,
        onDecision: @escaping (ApprovalUserChoice) -> Void
    ) {
        self.request = request
        self.hapticsEnabled = hapticsEnabled
        self.timerEnabled = timerEnabled
        self.onDecision = onDecision
        _remainingSeconds = State(initialValue: request.timeoutSeconds)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: RFSpacing.md) {
                    headerSection
                    inputSection
                    suggestedDecisionSection
                    buttonsSection
                }
                .padding(.horizontal, RFSpacing.md)
                .padding(.vertical, RFSpacing.sm)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(RFColors.fallbackBackground)
            .navigationTitle(String(localized: "approval.sheet.title"))
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
        .interactiveDismissDisabled(!isDecided)
        .onAppear {
            if timerEnabled {
                startCountdown()
            }
        }
        .onDisappear {
            timerTask?.cancel()
            timerTask = nil
        }
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xs) {
            HStack(spacing: RFSpacing.sm) {
                Image(systemName: toolIconName)
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(riskColor)
                    .frame(width: 30)

                VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                    RFText(toolDisplayName, style: .headline)
                    RFText(
                        String(localized: "approval.sheet.subtitle"),
                        style: .caption,
                        color: RFColors.fallbackTextSecondary
                    )
                }
                Spacer(minLength: 0)
                riskBadge
            }

            HStack(spacing: RFSpacing.xxs) {
                Image(systemName: "timer")
                    .font(.caption)
                    .foregroundStyle(remainingColor)
                let countdownTemplate = String(
                    localized: "approval.sheet.countdown %lld"
                )
                RFText(
                    String.localizedStringWithFormat(countdownTemplate, remainingSeconds),
                    style: .captionBold,
                    color: remainingColor
                )
                Spacer(minLength: 0)
            }
        }
    }

    // MARK: - Input Preview

    private var inputSection: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                RFText(
                    String(localized: "approval.sheet.input"),
                    style: .captionBold,
                    color: RFColors.fallbackTextSecondary
                )
                inputBody
            }
        }
    }

    @ViewBuilder
    private var inputBody: some View {
        let preview = request.inputPreview ?? ""
        if preview.isEmpty {
            RFText(
                String(localized: "approval.sheet.input.empty"),
                style: .body,
                color: RFColors.fallbackTextTertiary
            )
        } else {
            let isOverflow = preview.count > Self.inputPreviewLimit
            let display: String = {
                if isOverflow && !isPromptExpanded {
                    let endIndex = preview.index(
                        preview.startIndex,
                        offsetBy: Self.inputPreviewLimit
                    )
                    return String(preview[..<endIndex]) + "…"
                }
                return preview
            }()

            Text(display)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(RFColors.fallbackTextPrimary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)

            if isOverflow {
                Button {
                    if hapticsEnabled { HapticManager.selection() }
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isPromptExpanded.toggle()
                    }
                } label: {
                    HStack(spacing: RFSpacing.xxs) {
                        Image(systemName: isPromptExpanded ? "chevron.up" : "chevron.down")
                            .font(.caption2)
                        RFText(
                            isPromptExpanded
                                ? String(localized: "approval.sheet.input.showLess")
                                : String(localized: "approval.sheet.input.showFull"),
                            style: .captionBold,
                            color: RFColors.fallbackPrimary
                        )
                    }
                }
                .buttonStyle(.plain)
            }
        }
    }

    // MARK: - Suggested Decision Hint

    private var suggestedDecisionSection: some View {
        RFCard {
            HStack(spacing: RFSpacing.sm) {
                Image(systemName: "lightbulb.fill")
                    .font(.body)
                    .foregroundStyle(RFColors.warning)
                VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                    RFText(
                        String(localized: "approval.sheet.suggested"),
                        style: .captionBold,
                        color: RFColors.fallbackTextSecondary
                    )
                    RFText(
                        suggestedDecisionLabel,
                        style: .body
                    )
                }
                Spacer(minLength: 0)
            }
        }
    }

    // MARK: - Buttons

    private var buttonsSection: some View {
        VStack(spacing: RFSpacing.xs) {
            decisionButton(
                title: String(localized: "approval.sheet.button.allowOnce"),
                style: .primary,
                systemImage: "checkmark.circle"
            ) {
                handleDecision(.allowOnce)
            }

            decisionButton(
                title: String(localized: "approval.sheet.button.allowSession"),
                style: .secondary,
                systemImage: "checkmark.circle.badge.questionmark"
            ) {
                handleDecision(.allowSession)
            }

            decisionButton(
                title: String(localized: "approval.sheet.button.deny"),
                style: .danger,
                systemImage: "xmark.circle"
            ) {
                handleDecision(.deny)
            }
        }
    }

    private func decisionButton(
        title: String,
        style: ApprovalSheetButtonStyle,
        systemImage: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: RFSpacing.sm) {
                Image(systemName: systemImage)
                    .font(.body.weight(.semibold))
                RFText(title, style: .bodyBold, color: foregroundColor(for: style))
                Spacer(minLength: 0)
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(backgroundColor(for: style))
            .foregroundStyle(foregroundColor(for: style))
            .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))
        }
        .buttonStyle(.plain)
        .disabled(isDecided)
        .accessibilityLabel(title)
    }

    private enum ApprovalSheetButtonStyle {
        case primary, secondary, danger
    }

    private func backgroundColor(for style: ApprovalSheetButtonStyle) -> Color {
        switch style {
        case .primary: return RFColors.fallbackPrimary
        case .secondary: return RFColors.fallbackSurface
        case .danger: return RFColors.error.opacity(0.15)
        }
    }

    private func foregroundColor(for style: ApprovalSheetButtonStyle) -> Color {
        switch style {
        case .primary: return .white
        case .secondary: return RFColors.fallbackTextPrimary
        case .danger: return RFColors.error
        }
    }

    // MARK: - Decision

    private func handleDecision(_ choice: ApprovalUserChoice) {
        guard !isDecided else { return }
        isDecided = true
        timerTask?.cancel()
        timerTask = nil

        if hapticsEnabled {
            switch choice {
            case .allowOnce: HapticManager.success()
            case .allowSession: HapticManager.bookmarked()
            case .deny: HapticManager.warning()
            }
        }
        onDecision(choice)
    }

    private func startCountdown() {
        timerTask?.cancel()
        timerTask = Task { @MainActor in
            while remainingSeconds > 0 && !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard !Task.isCancelled else { return }
                remainingSeconds = max(remainingSeconds - 1, 0)
            }

            guard !Task.isCancelled, !isDecided else { return }
            // 30s timeout -> auto deny (Spike #5).
            handleDecision(.deny)
        }
    }

    // MARK: - Helpers

    private var toolIconName: String {
        switch request.policy {
        case .autoAllow:
            return "lock.open"
        case .prompt(.high), .autoDenyOnTimeout:
            return "exclamationmark.triangle.fill"
        case .prompt(.medium):
            return "questionmark.circle.fill"
        case .prompt(.low):
            return "info.circle.fill"
        }
    }

    private var toolDisplayName: String {
        Self.localizedToolName(request.toolName)
    }

    /// Tool ismi -> Türkçe dostu gösterim. Bilinmiyorsa orijinal adi dondurur.
    nonisolated static func localizedToolName(_ name: String) -> String {
        switch name.lowercased() {
        case "read": return String(localized: "approval.tool.read")
        case "edit": return String(localized: "approval.tool.edit")
        case "write": return String(localized: "approval.tool.write")
        case "bash": return String(localized: "approval.tool.bash")
        case "grep": return String(localized: "approval.tool.grep")
        case "ls", "glob": return String(localized: "approval.tool.list")
        default:
            if name == "WebFetch" {
                return String(localized: "approval.tool.webFetch")
            }
            if name == "WebSearch" {
                return String(localized: "approval.tool.webSearch")
            }
            return name
        }
    }

    private var riskColor: Color {
        switch request.policy {
        case .prompt(.high), .autoDenyOnTimeout: return RFColors.error
        case .prompt(.medium): return RFColors.warning
        case .prompt(.low), .autoAllow: return RFColors.fallbackPrimary
        }
    }

    private var riskBadge: some View {
        let label: String
        let color: Color
        switch request.policy {
        case .prompt(.high), .autoDenyOnTimeout:
            label = String(localized: "approval.sheet.risk.high")
            color = RFColors.error
        case .prompt(.medium):
            label = String(localized: "approval.sheet.risk.medium")
            color = RFColors.warning
        case .prompt(.low), .autoAllow:
            label = String(localized: "approval.sheet.risk.low")
            color = RFColors.success
        }
        return RFText(label, style: .captionBold, color: color)
            .padding(.horizontal, RFSpacing.xs)
            .padding(.vertical, RFSpacing.xxs)
            .background(color.opacity(0.15))
            .clipShape(Capsule())
    }

    private var suggestedDecisionLabel: String {
        switch request.policy {
        case .autoAllow: return String(localized: "approval.sheet.suggested.allow")
        case .prompt(.high), .autoDenyOnTimeout: return String(localized: "approval.sheet.suggested.deny")
        case .prompt(.medium), .prompt(.low): return String(localized: "approval.sheet.suggested.ask")
        }
    }

    private var remainingColor: Color {
        if remainingSeconds <= 5 { return RFColors.error }
        if remainingSeconds <= 15 { return RFColors.warning }
        return RFColors.fallbackTextSecondary
    }
}

// MARK: - Sheet Request DTO

/// Sheet'in render edebilecegi minimal payload — coordinator/view tarafindan
/// uretilir. Tool ismi + giris onizlemesi + politika yeter.
struct ApprovalSheetRequest: Identifiable, Sendable, Equatable {
    let id: String
    let toolName: String
    let inputPreview: String?
    let policy: ApprovalDecisionPolicy
    let timeoutSeconds: Int

    init(
        id: String = UUID().uuidString,
        toolName: String,
        inputPreview: String? = nil,
        policy: ApprovalDecisionPolicy,
        timeoutSeconds: Int = 30
    ) {
        self.id = id
        self.toolName = toolName
        self.inputPreview = inputPreview
        self.policy = policy
        self.timeoutSeconds = timeoutSeconds
    }
}

// MARK: - Preview

#Preview("High risk — bash rm") {
    RFApprovalSheet(
        request: ApprovalSheetRequest(
            toolName: "Bash",
            inputPreview: "rm -rf /tmp/build-cache",
            policy: .prompt(risk: .high),
            timeoutSeconds: 30
        ),
        onDecision: { _ in }
    )
}

#Preview("Medium risk — Edit") {
    RFApprovalSheet(
        request: ApprovalSheetRequest(
            toolName: "Edit",
            inputPreview: "src/server.py: replace `print(...)` with `logger.info(...)`",
            policy: .prompt(risk: .medium),
            timeoutSeconds: 30
        ),
        onDecision: { _ in }
    )
}

#Preview("Network — WebFetch") {
    RFApprovalSheet(
        request: ApprovalSheetRequest(
            toolName: "WebFetch",
            inputPreview: "https://api.anthropic.com/v1/messages",
            policy: .prompt(risk: .medium),
            timeoutSeconds: 30
        ),
        onDecision: { _ in }
    )
}
