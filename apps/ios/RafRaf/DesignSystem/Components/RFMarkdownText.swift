import SwiftUI

/// Markdown destekli metin bileseni.
/// Assistant mesajlari icin **bold**, *italic*, `inline code` ve listeler render eder.
/// Fallback olarak duz metin gosterir.
struct RFMarkdownText: View {
    let content: String
    let style: RFTextStyle
    let color: Color?

    init(
        _ content: String,
        style: RFTextStyle = .body,
        color: Color? = nil
    ) {
        self.content = content
        self.style = style
        self.color = color
    }

    var body: some View {
        Text(attributedContent)
            .font(style.font)
            .foregroundStyle(color ?? style.color)
    }

    private var attributedContent: AttributedString {
        let options = AttributedString.MarkdownParsingOptions(
            allowsExtendedAttributes: true,
            interpretedSyntax: .inlineOnlyPreservingWhitespace
        )
        guard let attributed = try? AttributedString(markdown: content, options: options) else {
            return AttributedString(content)
        }
        return attributed
    }
}

#Preview {
    VStack(alignment: .leading, spacing: RFSpacing.md) {
        RFMarkdownText("Regular text without markdown", style: .body)
        RFMarkdownText("**Bold text** and *italic text*", style: .body)
        RFMarkdownText("Use `inline code` for commands", style: .body)
        RFMarkdownText("**Status**: All systems `online`", style: .body, color: .green)
    }
    .padding()
}
