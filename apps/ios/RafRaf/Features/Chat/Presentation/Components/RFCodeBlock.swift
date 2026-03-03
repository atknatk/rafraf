import SwiftUI

/// Kod blogu goruntuleme bileseni.
/// Syntax highlighted kod gosterimi ve tek tikla kopyalama destegi.
struct RFCodeBlock: View {
    let code: String
    let language: String?
    let onCopy: ((String) -> Void)?

    @State private var isCopied: Bool = false

    init(
        code: String,
        language: String? = nil,
        onCopy: ((String) -> Void)? = nil
    ) {
        self.code = code
        self.language = language
        self.onCopy = onCopy
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            headerView

            ScrollView(.horizontal, showsIndicators: false) {
                RFText(code, style: .body)
                    .font(.system(.body, design: .monospaced))
                    .foregroundStyle(RFColors.fallbackTextPrimary)
                    .padding(RFSpacing.sm)
            }
            .background(codeBackground)
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(RFColors.divider, lineWidth: 0.5)
        )
    }

    // MARK: - Subviews

    private var headerView: some View {
        HStack {
            if let language {
                RFText(language, style: .captionBold, color: RFColors.fallbackTextSecondary)
            }
            Spacer()
            RFButton(
                isCopied
                    ? String(localized: "chat.code.copied")
                    : String(localized: "chat.code.copy"),
                style: .ghost,
                size: .small
            ) {
                copyCode()
            }
        }
        .padding(.horizontal, RFSpacing.sm)
        .padding(.vertical, RFSpacing.xxs)
        .background(RFColors.fallbackSurface)
    }

    private var codeBackground: Color {
        RFColors.fallbackSurface.opacity(0.5)
    }

    // MARK: - Actions

    private func copyCode() {
        onCopy?(code)
        UIPasteboard.general.string = code
        isCopied = true

        Task { @MainActor in
            try? await Task.sleep(for: .seconds(2))
            isCopied = false
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFCodeBlock(
            code: "func greet(name: String) -> String {\n    return \"Hello, \\(name)!\"\n}",
            language: "swift"
        )

        RFCodeBlock(
            code: "print(\"Hello World\")",
            language: "python"
        )
    }
    .padding()
}
