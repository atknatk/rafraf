import Factory
import SwiftUI

/// V1.x SLIM (Item 11) — Claude subprocess supervisor inline banner.
///
/// Spec: `shared/feature-specs/V1x-claude-supervisor.md` §3 (state machine),
/// §7 (presentation slim scope: history view + detail sheet DEFERRED).
///
/// Banner state machine:
///   - running / idle / completed / starting → banner GIZLI (state nil)
///   - stale: yellow + "Subprocess hung" + Diagnosing... spinner
///   - diagnosing: blue + diagnosis text streaming
///   - rate_limited: orange + "Rate limited until {time}"
///   - crashed: red + "Subprocess crashed (exit code N)" + Retry button
///   - recovered: green flash + "Recovered" then auto-dismiss after 3s
///
/// Tum kullanici metni `String(localized:)` uzerinden lokalize edilir.
/// Reduce-motion: sadece opacity transition kullanilir, scale/spring atlanir.
/// VoiceOver: container `.accessibilityElement(children: .combine)` ile tek
/// nesne gibi okunur; durum + detail combined.
struct RFClaudeProcessBanner: View {
    let sessionId: String

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var bannerState: ClaudeProcessBannerState?
    @State private var observeTask: Task<Void, Never>?

    private let repository: ClaudeProcessRepository
    private let retryUseCase: RetryClaudeProcessUseCase

    init(
        sessionId: String,
        repository: ClaudeProcessRepository = Container.shared.claudeProcessRepository(),
        retryUseCase: RetryClaudeProcessUseCase = Container.shared.retryClaudeProcessUseCase()
    ) {
        self.sessionId = sessionId
        self.repository = repository
        self.retryUseCase = retryUseCase
    }

    var body: some View {
        Group {
            if let state = bannerState {
                bannerContent(for: state)
                    .transition(reduceMotion
                        ? .opacity
                        : .move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.25), value: bannerState?.state)
        .task(id: sessionId) {
            observeTask?.cancel()
            observeTask = Task { @MainActor in
                let stream = await repository.observeBanner(sessionId: sessionId)
                for await snapshot in stream {
                    bannerState = snapshot
                }
            }
        }
    }

    // MARK: - Banner Content

    @ViewBuilder
    private func bannerContent(for state: ClaudeProcessBannerState) -> some View {
        HStack(alignment: .top, spacing: RFSpacing.sm) {
            iconView(for: state.state)
                .frame(width: 24, height: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(titleText(for: state))
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(textForeground(for: state.state))
                if let subtitle = subtitleText(for: state) {
                    Text(subtitle)
                        .font(.system(size: 12))
                        .foregroundStyle(textForeground(for: state.state).opacity(0.9))
                        .lineLimit(2)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            // Action area — Retry (crashed) + Dismiss
            if state.state == .crashed {
                Button {
                    Task { await onRetryTapped() }
                } label: {
                    Text(String(localized: "claude.process.banner.retry"))
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, RFSpacing.sm)
                        .padding(.vertical, RFSpacing.xxs)
                        .background(
                            Capsule().fill(Color.white.opacity(0.25))
                        )
                }
                .buttonStyle(.plain)
                .accessibilityLabel(String(localized: "claude.process.banner.retry.a11y"))
                .accessibilityHint(String(localized: "claude.process.banner.retry.hint"))
            }

            Button {
                Task { await repository.dismissBanner(sessionId: sessionId) }
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(textForeground(for: state.state).opacity(0.7))
            }
            .buttonStyle(.plain)
            .accessibilityLabel(String(localized: "claude.process.banner.dismiss.a11y"))
        }
        .padding(.horizontal, RFSpacing.md)
        .padding(.vertical, RFSpacing.sm)
        .frame(maxWidth: .infinity)
        .background(backgroundColor(for: state.state))
        .overlay(alignment: .bottom) { Divider() }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel(for: state))
    }

    // MARK: - Icon

    @ViewBuilder
    private func iconView(for state: ClaudeProcessState) -> some View {
        switch state {
        case .stale:
            ProgressView()
                .controlSize(.small)
                .tint(.white)
        case .diagnosing:
            ProgressView()
                .controlSize(.small)
                .tint(.white)
        case .rateLimited:
            Image(systemName: "hourglass")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(.white)
        case .crashed:
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(.white)
        case .recovered:
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(.white)
        default:
            Image(systemName: "info.circle")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(.white)
        }
    }

    // MARK: - Background / Foreground

    private func backgroundColor(for state: ClaudeProcessState) -> Color {
        switch state {
        case .stale: return RFColors.warning
        case .diagnosing: return RFColors.info
        case .rateLimited: return Color(red: 0.95, green: 0.55, blue: 0.20)
        case .crashed: return RFColors.error
        case .recovered: return RFColors.success
        default: return RFColors.fallbackTextTertiary
        }
    }

    private func textForeground(for state: ClaudeProcessState) -> Color {
        // Tum durumlarda beyaz metin — colorblind / contrast WCAG AA korunur
        // (banner background semantic renk +60 luminance kontrasti).
        .white
    }

    // MARK: - Text

    private func titleText(for state: ClaudeProcessBannerState) -> String {
        switch state.state {
        case .stale:
            return String(localized: "claude.process.banner.stale.title")
        case .diagnosing:
            return String(localized: "claude.process.banner.diagnosing.title")
        case .rateLimited:
            return String(localized: "claude.process.banner.rateLimited.title")
        case .crashed:
            if let code = state.exitCode {
                let template = String(localized: "claude.process.banner.crashed.title")
                return String(format: template, code)
            }
            return String(localized: "claude.process.banner.crashed.title.generic")
        case .recovered:
            return String(localized: "claude.process.banner.recovered.title")
        default:
            return ""
        }
    }

    private func subtitleText(for state: ClaudeProcessBannerState) -> String? {
        switch state.state {
        case .stale:
            return String(localized: "claude.process.banner.stale.subtitle")
        case .diagnosing:
            // Diagnosis text bridge tarafindan English uretiliyor — Q7 karari.
            return state.detail
        case .rateLimited:
            if let resets = state.rateLimitResetsAt {
                let formatter = DateFormatter()
                formatter.timeStyle = .short
                let timeString = formatter.string(from: resets)
                let template = String(localized: "claude.process.banner.rateLimited.subtitle")
                return String(format: template, timeString)
            }
            return nil
        case .crashed:
            return state.detail.map { String($0.prefix(140)) }
        case .recovered:
            return nil
        default:
            return nil
        }
    }

    private func accessibilityLabel(for state: ClaudeProcessBannerState) -> String {
        let title = titleText(for: state)
        if let subtitle = subtitleText(for: state) {
            return "\(title). \(subtitle)"
        }
        return title
    }

    // MARK: - Retry

    private func onRetryTapped() async {
        do {
            try await retryUseCase.execute(sessionId: sessionId)
        } catch {
            // Retry hatasi sessizce yutulmaz — banner zaten crashed durumunda;
            // kullanici bir kez daha basabilir. Logger seviyesinde tutuyoruz.
            AppLogger.logger(for: "RFClaudeProcessBanner")
                .error("retry hatasi: \(error.localizedDescription, privacy: .public)")
        }
    }
}

#Preview("Crashed") {
    let repo = ClaudeProcessRepositoryImpl()
    Task {
        await repo.applySpawned(
            sessionId: "preview-1",
            pid: 12345,
            startedAt: Date(),
            model: "claude-sonnet-4-7",
            projectDir: nil
        )
        await repo.applyCrashed(
            sessionId: "preview-1",
            exitCode: 137,
            signal: "SIGKILL",
            stderrTail: "Error: connection reset by peer",
            observedAt: Date()
        )
    }
    return VStack {
        RFClaudeProcessBanner(
            sessionId: "preview-1",
            repository: repo,
            retryUseCase: RetryClaudeProcessUseCase(repository: repo)
        )
        Spacer()
    }
    .background(Color(.systemBackground))
}

#Preview("Stale") {
    let repo = ClaudeProcessRepositoryImpl()
    Task {
        await repo.applySpawned(
            sessionId: "preview-2",
            pid: 12346,
            startedAt: Date(),
            model: "claude-sonnet-4-7",
            projectDir: nil
        )
        await repo.applyStalled(
            sessionId: "preview-2",
            stderrTail: "Awaiting tool result...",
            observedAt: Date()
        )
    }
    return VStack {
        RFClaudeProcessBanner(
            sessionId: "preview-2",
            repository: repo,
            retryUseCase: RetryClaudeProcessUseCase(repository: repo)
        )
        Spacer()
    }
    .background(Color(.systemBackground))
}
