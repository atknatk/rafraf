import SwiftUI

/// Mesaj baloncugu bileseni — Claude-inspired sicak tonlar.
/// Kullanici balonlari sicak tan, AI mesajlari minimal/full-width.
struct RFMessageBubble: View {
    let message: ChatMessage
    let onCopy: ((String) -> Void)?
    let onImageTap: ((String) -> Void)?

    init(
        message: ChatMessage,
        onCopy: ((String) -> Void)? = nil,
        onImageTap: ((String) -> Void)? = nil
    ) {
        self.message = message
        self.onCopy = onCopy
        self.onImageTap = onImageTap
    }

    var body: some View {
        HStack {
            if message.sender == .user {
                Spacer(minLength: RFSpacing.xxxl)
            }

            VStack(alignment: bubbleAlignment, spacing: RFSpacing.xxs) {
                if message.sender == .system {
                    systemMessageView
                } else {
                    bubbleContentView
                }

                RFText(
                    formattedTimestamp,
                    style: .caption,
                    color: RFColors.fallbackTextTertiary
                )
            }

            if message.sender == .assistant || message.sender == .system {
                Spacer(minLength: RFSpacing.xxl)
            }
        }
        .contextMenu {
            Button {
                onCopy?(message.content)
            } label: {
                Label(
                    String(localized: "chat.message.copy"),
                    systemImage: "doc.on.doc"
                )
            }
        }
    }

    // MARK: - Subviews

    @ViewBuilder
    private var bubbleContentView: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xs) {
            switch message.type {
            case .code:
                RFCodeBlock(code: message.content, onCopy: onCopy)
            case .image:
                if let firstAttachment = message.attachments.first {
                    RFImageMessageView(
                        url: firstAttachment.url,
                        onTap: { onImageTap?(firstAttachment.url) }
                    )
                }
                if !message.content.isEmpty {
                    messageTextView
                }
            case .file:
                fileAttachmentView
                if !message.content.isEmpty {
                    messageTextView
                }
            case .text, .system:
                messageTextView
            }

            if message.isStreaming {
                streamingIndicator
            }
        }
        .padding(.horizontal, RFSpacing.sm)
        .padding(.vertical, RFSpacing.xs + 2)
        .background(bubbleBackgroundColor)
        .clipShape(
            RoundedRectangle(
                cornerRadius: message.sender == .user
                    ? RFCornerRadius.large
                    : RFCornerRadius.medium
            )
        )
    }

    private var messageTextView: some View {
        RFText(
            message.content,
            style: .body,
            color: bubbleTextColor
        )
    }

    private var systemMessageView: some View {
        RFText(
            message.content,
            style: .caption,
            color: RFColors.fallbackTextSecondary
        )
        .padding(.horizontal, RFSpacing.md)
        .padding(.vertical, RFSpacing.xs)
        .background(RFColors.fallbackSurface.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))
    }

    private var fileAttachmentView: some View {
        HStack(spacing: RFSpacing.xs) {
            Image(systemName: "doc.fill")
                .foregroundStyle(bubbleTextColor.opacity(0.6))
            if let attachment = message.attachments.first {
                VStack(alignment: .leading, spacing: 2) {
                    RFText(
                        attachment.url.components(separatedBy: "/").last ?? String(localized: "chat.file.unknown"),
                        style: .bodyBold,
                        color: bubbleTextColor
                    )
                    RFText(
                        formattedFileSize(attachment.sizeBytes),
                        style: .caption,
                        color: bubbleTextColor.opacity(0.6)
                    )
                }
            }
        }
    }

    private var streamingIndicator: some View {
        HStack(spacing: RFSpacing.xxs) {
            ForEach(0..<3, id: \.self) { _ in
                Circle()
                    .fill(bubbleTextColor.opacity(0.3))
                    .frame(width: 4, height: 4)
            }
        }
    }

    // MARK: - Computed Properties

    private var bubbleAlignment: HorizontalAlignment {
        switch message.sender {
        case .user: return .trailing
        case .assistant: return .leading
        case .system: return .center
        }
    }

    private var bubbleBackgroundColor: Color {
        switch message.sender {
        case .user: return RFColors.userBubble
        case .assistant: return RFColors.aiBubble
        case .system: return RFColors.fallbackSurface
        }
    }

    private var bubbleTextColor: Color {
        RFColors.fallbackTextPrimary
    }

    private var formattedTimestamp: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: message.timestamp)
    }

    private func formattedFileSize(_ bytes: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(bytes))
    }
}

#Preview {
    ScrollView {
        VStack(spacing: RFSpacing.sm) {
            RFMessageBubble(
                message: ChatMessage(
                    content: "Merhaba, projemin durumunu kontrol eder misin?",
                    sender: .user
                )
            )

            RFMessageBubble(
                message: ChatMessage(
                    content: "Tabii, projenizi kontrol ediyorum. Sonuclari hemen paylasacagim.",
                    sender: .assistant
                )
            )

            RFMessageBubble(
                message: ChatMessage(
                    content: "Oturum basladi",
                    sender: .system,
                    type: .system
                )
            )

            RFMessageBubble(
                message: ChatMessage(
                    content: "func hello() {\n    print(\"World\")\n}",
                    sender: .assistant,
                    type: .code
                )
            )
        }
        .padding()
    }
    .background(RFColors.fallbackBackground)
}
