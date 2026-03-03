import SwiftUI

/// RafRaf tool calistirma durum gostergesi.
/// AI'nin tool kullandigini ve hangi tool'un calistigini animasyonlu gosterir.
struct RFToolStatusView: View {
    /// Tool adi.
    let toolName: String
    /// Yapilan islem.
    let action: String
    /// Tool calisiyor mu.
    let isRunning: Bool

    @State private var dotCount: Int = 0

    var body: some View {
        HStack(spacing: RFSpacing.xs) {
            // Tool ikonu
            Image(systemName: iconName(for: toolName))
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(isRunning ? RFColors.fallbackPrimary : RFColors.success)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 2) {
                RFText(toolName, style: .captionBold)

                HStack(spacing: 2) {
                    RFText(action, style: .caption, color: RFColors.fallbackTextSecondary)

                    if isRunning {
                        RFText(
                            String(repeating: ".", count: dotCount + 1),
                            style: .caption,
                            color: RFColors.fallbackTextSecondary
                        )
                    }
                }
            }

            Spacer()

            if isRunning {
                ProgressView()
                    .controlSize(.mini)
            } else {
                Image(systemName: "checkmark")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(RFColors.success)
            }
        }
        .padding(.horizontal, RFSpacing.sm)
        .padding(.vertical, RFSpacing.xs)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(RFColors.fallbackSurface)
        )
        .task(id: isRunning) {
            guard isRunning else { return }
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(500))
                guard !Task.isCancelled else { return }
                dotCount = (dotCount + 1) % 3
            }
        }
    }

    // MARK: - Private

    private func iconName(for tool: String) -> String {
        let lowered = tool.lowercased()
        if lowered.contains("docker") {
            return "shippingbox"
        } else if lowered.contains("playwright") || lowered.contains("browser") {
            return "globe"
        } else if lowered.contains("shell") || lowered.contains("terminal") {
            return "terminal"
        } else if lowered.contains("maestro") {
            return "iphone"
        } else if lowered.contains("git") {
            return "arrow.triangle.branch"
        } else {
            return "wrench.and.screwdriver"
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.sm) {
        RFToolStatusView(
            toolName: "docker",
            action: "build",
            isRunning: true
        )

        RFToolStatusView(
            toolName: "playwright",
            action: "navigate",
            isRunning: false
        )

        RFToolStatusView(
            toolName: "shell",
            action: "npm test",
            isRunning: true
        )
    }
    .padding()
}
