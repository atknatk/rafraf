import SwiftUI

/// Mesaj baloncugu bileseni — Claude-inspired sicak tonlar.
/// Kullanici balonlari sicak tan, AI mesajlari minimal/full-width.
struct RFMessageBubble: View {
    let message: ChatMessage
    let onCopy: ((String) -> Void)?
    let onImageTap: ((String) -> Void)?
    let onSpeak: (() -> Void)?

    init(
        message: ChatMessage,
        onCopy: ((String) -> Void)? = nil,
        onImageTap: ((String) -> Void)? = nil,
        onSpeak: (() -> Void)? = nil
    ) {
        self.message = message
        self.onCopy = onCopy
        self.onImageTap = onImageTap
        self.onSpeak = onSpeak
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

                HStack(spacing: RFSpacing.xs) {
                    RFText(
                        formattedTimestamp,
                        style: .caption,
                        color: RFColors.fallbackTextTertiary
                    )

                    if let onSpeak, message.sender == .assistant {
                        Button {
                            RFHaptics.impact(.light)
                            onSpeak()
                        } label: {
                            Image(systemName: "speaker.wave.2.fill")
                                .font(.caption2)
                                .foregroundStyle(RFColors.fallbackTextTertiary)
                        }
                        .buttonStyle(RFPressButtonStyle())
                    }
                }
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

            if let onSpeak, message.sender == .assistant {
                Button {
                    onSpeak()
                } label: {
                    Label(
                        String(localized: "chat.message.speak"),
                        systemImage: "speaker.wave.2.fill"
                    )
                }
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
            case .codeDiff:
                if let data = message.content.data(using: .utf8),
                   let payload = try? {
                       let dec = JSONDecoder()
                       dec.keyDecodingStrategy = .convertFromSnakeCase
                       return try dec.decode(CodeDiffPayloadDTO.self, from: data)
                   }() {
                    RFDiffBubble(payload: payload)
                } else {
                    messageTextView
                }
            case .text, .system:
                messageTextView
            }

            if message.isStreaming {
                streamingIndicator
            }

            // Token sayaci
            if message.sender == .assistant, let tokens = message.tokensUsed {
                tokenCostBadge(tokens: tokens, model: message.modelUsed)
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

    @ViewBuilder
    private func tokenCostBadge(tokens: Int, model: String?) -> some View {
        let costPerMillion: Double = {
            let m = (model ?? "").lowercased()
            if m.contains("haiku") { return 0.25 }
            if m.contains("opus") { return 15.0 }
            return 3.0
        }()
        let estimatedCost = Double(tokens) / 1_000_000.0 * costPerMillion

        HStack(spacing: 4) {
            Image(systemName: "bolt.fill")
                .font(.system(size: 9))
            Text("\(tokens) tok · $\(String(format: "%.5f", estimatedCost))")
                .font(.system(size: 10, weight: .medium, design: .monospaced))
        }
        .foregroundStyle(RFColors.fallbackTextTertiary)
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(RFColors.fallbackTextTertiary.opacity(0.08))
        .clipShape(Capsule())
        .frame(maxWidth: .infinity, alignment: .trailing)
        .padding(.top, 2)
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

// MARK: - RFDiffBubble

/// Code diff goruntuleme bileseni.
/// Claude'un dosya degisikliklerini satir satir gosterir.
struct RFDiffBubble: View {
    let payload: CodeDiffPayloadDTO
    @State private var expandedFiles: Set<String> = []

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xs) {
            // Header
            HStack {
                Image(systemName: "arrow.triangle.branch")
                    .foregroundStyle(RFColors.fallbackPrimary)
                RFText(
                    String(localized: "chat.diff.title"),
                    style: .captionBold,
                    color: RFColors.fallbackPrimary
                )
                Spacer()
                RFText(
                    "+\(payload.totalAdditions) -\(payload.totalDeletions)",
                    style: .caption
                )
            }

            // Dosyalar
            ForEach(payload.files, id: \.filePath) { file in
                diffFileRow(file: file)
            }
        }
        .padding(RFSpacing.sm)
        .background(RFColors.fallbackSurface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func diffFileRow(file: CodeDiffFileDTO) -> some View {
        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
            // Dosya basligi (tiklanabilir - expand/collapse)
            Button {
                if expandedFiles.contains(file.filePath) {
                    expandedFiles.remove(file.filePath)
                } else {
                    expandedFiles.insert(file.filePath)
                }
            } label: {
                HStack {
                    Image(systemName: expandedFiles.contains(file.filePath) ? "chevron.down" : "chevron.right")
                        .font(.system(size: 10))
                        .foregroundStyle(RFColors.fallbackTextSecondary)
                    RFText(
                        (file.filePath as NSString).lastPathComponent,
                        style: .caption,
                        color: RFColors.fallbackTextPrimary
                    )
                    Spacer()
                    RFText(
                        "+\(file.additions) -\(file.deletions)",
                        style: .caption,
                        color: RFColors.fallbackTextSecondary
                    )
                }
            }
            .buttonStyle(.plain)

            // Satirlar (expand edilmisse goster, max 30 satir)
            if expandedFiles.contains(file.filePath) {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(file.lines.prefix(30).enumerated()), id: \.offset) { _, line in
                        diffLineView(line: line)
                    }
                    if file.lines.count > 30 {
                        RFText(
                            String(localized: "chat.diff.moreLines.\(file.lines.count - 30)"),
                            style: .caption,
                            color: RFColors.fallbackTextTertiary
                        )
                        .padding(.leading, RFSpacing.xs)
                    }
                }
                .background(Color(.systemBackground).opacity(0.5))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }
        }
    }

    private func diffLineView(line: CodeDiffLineDTO) -> some View {
        HStack(spacing: RFSpacing.xxs) {
            // Tip rengi
            Rectangle()
                .fill(lineColor(for: line.type))
                .frame(width: 3)

            // Satir numarasi
            RFText(
                lineNumberText(line),
                style: .caption,
                color: RFColors.fallbackTextTertiary
            )
            .frame(width: 28, alignment: .trailing)
            .monospacedDigit()

            // Icerik
            Text(line.content)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(lineColor(for: line.type).opacity(line.type == "context" ? 0.7 : 1.0))
                .lineLimit(1)
        }
        .padding(.vertical, 1)
        .background(lineBgColor(for: line.type))
    }

    private func lineColor(for type: String) -> Color {
        switch type {
        case "added": return .green
        case "removed": return .red
        default: return RFColors.fallbackTextSecondary
        }
    }

    private func lineBgColor(for type: String) -> Color {
        switch type {
        case "added": return Color.green.opacity(0.08)
        case "removed": return Color.red.opacity(0.08)
        default: return Color.clear
        }
    }

    private func lineNumberText(_ line: CodeDiffLineDTO) -> String {
        if let num = line.lineNumberNew { return "\(num)" }
        if let num = line.lineNumberOld { return "\(num)" }
        return ""
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
