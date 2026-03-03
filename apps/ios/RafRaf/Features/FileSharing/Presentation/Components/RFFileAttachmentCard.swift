import SwiftUI

/// Chat icinde dosya eki karti.
/// Dosya bilgisi, boyut ve onizleme/indirme aksiyonu gosterir.
struct RFFileAttachmentCard: View {
    let file: SharedFile
    let isDownloading: Bool
    let onTap: () -> Void

    var body: some View {
        RFCard(style: .interactive, onTap: onTap) {
            HStack(spacing: RFSpacing.sm) {
                fileIcon
                fileInfo
                Spacer()
                actionIndicator
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(String(localized: "fileSharing.attachment.accessibilityLabel \(file.name)"))
        .accessibilityHint(String(localized: "fileSharing.attachment.accessibilityHint"))
    }

    // MARK: - File Icon

    private var fileIcon: some View {
        Image(systemName: iconName)
            .font(.title2)
            .foregroundStyle(RFColors.fallbackPrimary)
            .frame(width: 40, height: 40)
            .background(RFColors.fallbackPrimary.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private var iconName: String {
        let ext = (file.name as NSString).pathExtension.lowercased()
        switch ext {
        case "pdf": return "doc.fill"
        case "png", "jpg", "jpeg", "gif": return "photo.fill"
        case "txt", "md": return "doc.text.fill"
        case "py", "js", "ts", "swift": return "chevron.left.forwardslash.chevron.right"
        case "log": return "text.alignleft"
        case "zip": return "archivebox.fill"
        default: return "doc.fill"
        }
    }

    // MARK: - File Info

    private var fileInfo: some View {
        VStack(alignment: .leading, spacing: 2) {
            RFText(file.name, style: .bodyBold)
                .lineLimit(1)
            RFText(formattedSize, style: .caption)
        }
    }

    private var formattedSize: String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(file.size))
    }

    // MARK: - Action Indicator

    private var actionIndicator: some View {
        Group {
            if isDownloading {
                ProgressView()
                    .controlSize(.small)
            } else if file.localURL != nil {
                Image(systemName: "eye.fill")
                    .foregroundStyle(RFColors.fallbackPrimary)
            } else {
                Image(systemName: "arrow.down.circle.fill")
                    .foregroundStyle(RFColors.fallbackPrimary)
            }
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFFileAttachmentCard(
            file: SharedFile(
                id: "1",
                name: "rapor.pdf",
                fileKey: "projects/123/rapor.pdf",
                contentType: "application/pdf",
                size: 2_500_000,
                downloadURL: nil,
                localURL: nil
            ),
            isDownloading: false,
            onTap: {}
        )

        RFFileAttachmentCard(
            file: SharedFile(
                id: "2",
                name: "screenshot.png",
                fileKey: "projects/123/screenshot.png",
                contentType: "image/png",
                size: 450_000,
                downloadURL: nil,
                localURL: nil
            ),
            isDownloading: true,
            onTap: {}
        )
    }
    .padding()
}
