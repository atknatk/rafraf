import SwiftUI

/// Item 8 — Chat surface'inde aktif subagent sayisini gosteren kompakt pill.
///
/// Claude Code Task tool subagent spawn ettiginde kullanici sadece
/// AgentDetailView icindeki SubagentTreeView'da gorebiliyordu. Bu pill
/// `RFChatInput`'in hemen ustunde gorunur ve tap edilince ayni
/// SubagentTreeView'i sheet olarak acar.
///
/// Render kurali (ChatView): `count > 0` ise visible.
struct RFSubagentInlinePill: View {
    let count: Int
    let onTap: () -> Void

    @State private var pulse: Bool = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Button(action: {
            HapticManager.selection()
            onTap()
        }) {
            HStack(spacing: RFSpacing.xs) {
                ZStack {
                    Circle()
                        .fill(RFColors.fallbackPrimary.opacity(pulse ? 0.25 : 0.10))
                        .frame(width: 18, height: 18)
                    Image(systemName: "person.2.fill")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(RFColors.fallbackPrimary)
                }

                RFText(
                    titleText,
                    style: .captionBold,
                    color: RFColors.fallbackTextPrimary
                )

                Spacer(minLength: 0)

                Image(systemName: "chevron.right")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(RFColors.fallbackTextTertiary)
            }
            .padding(.horizontal, RFSpacing.sm)
            .padding(.vertical, RFSpacing.xs)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RFColors.fallbackSurface)
            .overlay(
                RoundedRectangle(cornerRadius: RFCornerRadius.medium)
                    .stroke(RFColors.fallbackPrimary.opacity(0.25), lineWidth: 0.5)
            )
            .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))
        }
        .buttonStyle(RFPressButtonStyle())
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(
                .easeInOut(duration: 1.1).repeatForever(autoreverses: true)
            ) {
                pulse = true
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(titleText)
        .accessibilityHint(String(localized: "chat.subagent.pill.hint"))
        .accessibilityAddTraits(.isButton)
    }

    private var titleText: String {
        // Pluralization icin String(localized:) Apple recommended pattern:
        // .stringsdict yoksa basit `count == 1` kontrolu yeterli (TR/EN).
        if count == 1 {
            return String(localized: "chat.subagent.pill.singular")
        }
        return String(format: String(localized: "chat.subagent.pill.plural"), count)
    }
}

#Preview("RFSubagentInlinePill — single") {
    VStack(spacing: 12) {
        RFSubagentInlinePill(count: 1, onTap: {})
        RFSubagentInlinePill(count: 3, onTap: {})
        RFSubagentInlinePill(count: 12, onTap: {})
    }
    .padding()
    .background(RFColors.fallbackBackground)
}
