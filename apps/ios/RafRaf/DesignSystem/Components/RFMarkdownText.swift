import MarkdownUI
import SwiftUI

/// Profesyonel markdown render bileseni — Claude/ChatGPT kalitesinde.
/// Headings, code blocks, tablolar, listeler, blockquote, bold/italic destekler.
/// RafRaf design system renkleri ve tipografisi ile uyumlu.
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
        Markdown(content)
            .markdownTheme(rafrafTheme)
            .markdownCodeSyntaxHighlighter(PlainTextCodeSyntaxHighlighter())
            .textSelection(.enabled)
    }

    // MARK: - RafRaf Theme

    private var rafrafTheme: Theme {
        Theme()
            // -- Text --
            .text {
                ForegroundColor(color ?? RFColors.fallbackTextPrimary)
                FontSize(style == .caption ? 13 : 15)
            }
            // -- Headings --
            .heading1 { configuration in
                configuration.label
                    .markdownMargin(top: 16, bottom: 8)
                    .markdownTextStyle {
                        FontWeight(.bold)
                        FontSize(22)
                        ForegroundColor(color ?? RFColors.fallbackTextPrimary)
                    }
            }
            .heading2 { configuration in
                configuration.label
                    .markdownMargin(top: 14, bottom: 6)
                    .markdownTextStyle {
                        FontWeight(.bold)
                        FontSize(19)
                        ForegroundColor(color ?? RFColors.fallbackTextPrimary)
                    }
            }
            .heading3 { configuration in
                configuration.label
                    .markdownMargin(top: 12, bottom: 4)
                    .markdownTextStyle {
                        FontWeight(.semibold)
                        FontSize(17)
                        ForegroundColor(color ?? RFColors.fallbackTextPrimary)
                    }
            }
            .heading4 { configuration in
                configuration.label
                    .markdownMargin(top: 10, bottom: 4)
                    .markdownTextStyle {
                        FontWeight(.semibold)
                        FontSize(15)
                        ForegroundColor(color ?? RFColors.fallbackTextPrimary)
                    }
            }
            // -- Strong / Emphasis --
            .strong {
                FontWeight(.semibold)
            }
            .emphasis {
                FontStyle(.italic)
            }
            .strikethrough {
                StrikethroughStyle(.single)
            }
            // -- Inline Code --
            .code {
                FontFamilyVariant(.monospaced)
                FontSize(.em(0.88))
                BackgroundColor(Color(.systemGray6))
                ForegroundColor(RFColors.fallbackPrimary)
            }
            // -- Code Block --
            .codeBlock { configuration in
                codeBlockView(configuration)
            }
            // -- Blockquote --
            .blockquote { configuration in
                HStack(spacing: 0) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(RFColors.fallbackPrimary.opacity(0.5))
                        .frame(width: 3)
                    configuration.label
                        .markdownTextStyle {
                            ForegroundColor(RFColors.fallbackTextSecondary)
                            FontSize(14)
                        }
                        .padding(.leading, 10)
                }
                .markdownMargin(top: 8, bottom: 8)
            }
            // -- Lists --
            .listItem { configuration in
                configuration.label
                    .markdownMargin(top: 2, bottom: 2)
            }
            // -- Table --
            .table { configuration in
                configuration.label
                    .markdownMargin(top: 8, bottom: 8)
                    .markdownTableBorderStyle(
                        .init(color: .secondary.opacity(0.3), width: 0.5)
                    )
                    .markdownTableBackgroundStyle(
                        .alternatingRows(Color.clear, Color(.systemGray6).opacity(0.5))
                    )
            }
            .tableCell { configuration in
                configuration.label
                    .markdownTextStyle {
                        FontSize(13)
                    }
                    .padding(.vertical, 4)
                    .padding(.horizontal, 8)
            }
            // -- Thematic Break (---) --
            .thematicBreak {
                Divider()
                    .padding(.vertical, 8)
            }
            // -- Links --
            .link {
                ForegroundColor(RFColors.fallbackPrimary)
                UnderlineStyle(.single)
            }
            // -- Paragraph spacing --
            .paragraph { configuration in
                configuration.label
                    .markdownMargin(top: 4, bottom: 4)
            }
            // -- Image (placeholder for chat) --
            .image { configuration in
                configuration.label
            }
    }

    // MARK: - Code Block View

    @ViewBuilder
    private func codeBlockView(_ configuration: CodeBlockConfiguration) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header with language + copy button
            HStack {
                if let language = configuration.language {
                    Text(language.uppercased())
                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                        .foregroundStyle(RFColors.fallbackTextTertiary)
                }
                Spacer()
                CopyButton(text: configuration.content)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(codeHeaderBackground)

            // Code content
            ScrollView(.horizontal, showsIndicators: false) {
                configuration.label
                    .markdownTextStyle {
                        FontFamilyVariant(.monospaced)
                        FontSize(13)
                        ForegroundColor(Color(.label))
                    }
                    .padding(12)
            }
        }
        .background(codeBackground)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .markdownMargin(top: 8, bottom: 8)
    }

    private var codeBackground: Color {
        Color(.systemGray6)
    }

    private var codeHeaderBackground: Color {
        Color(.systemGray5)
    }
}

// MARK: - Copy Button

private struct CopyButton: View {
    let text: String
    @State private var copied = false

    var body: some View {
        Button {
            UIPasteboard.general.string = text
            copied = true
            let generator = UIImpactFeedbackGenerator(style: .light)
            generator.impactOccurred()
            Task {
                try? await Task.sleep(for: .seconds(2))
                copied = false
            }
        } label: {
            HStack(spacing: 3) {
                Image(systemName: copied ? "checkmark" : "doc.on.doc")
                    .font(.system(size: 11))
                Text(copied ? String(localized: "code.copied") : String(localized: "code.copy"))
                    .font(.system(size: 11, weight: .medium))
            }
            .foregroundStyle(copied ? .green : RFColors.fallbackTextSecondary)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Plain Text Syntax Highlighter (fallback)

struct PlainTextCodeSyntaxHighlighter: CodeSyntaxHighlighter {
    func highlightCode(_ content: String, language: String?) -> Text {
        Text(content)
    }
}

// MARK: - Preview

#Preview {
    ScrollView {
        VStack(alignment: .leading, spacing: RFSpacing.md) {
            RFMarkdownText("""
            # Heading 1
            ## Heading 2
            ### Heading 3

            Regular text with **bold** and *italic* and `inline code`.

            > This is a blockquote with important info.

            - Bullet list item 1
            - Bullet list item 2
            - Bullet list item 3

            1. Ordered item
            2. Another item

            ```swift
            func hello() {
                print("Hello, World!")
            }
            ```

            | Column 1 | Column 2 |
            |----------|----------|
            | Cell A   | Cell B   |
            | Cell C   | Cell D   |

            ---

            A [link](https://rafraf.app) and ~~strikethrough~~.
            """, style: .body)
        }
        .padding()
    }
}
