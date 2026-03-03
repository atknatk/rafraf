import SwiftUI

/// Dosya yukleme ilerleme gorunumu.
/// Linear progress bar ve yuzdelik gosterim saglar.
struct RFUploadProgressView: View {
    let progress: FileUploadProgress

    var body: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                headerView
                progressBarView
                detailView
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            String(localized: "fileSharing.upload.accessibilityLabel \(progress.fileName)")
        )
        .accessibilityValue(
            String(localized: "fileSharing.upload.accessibilityValue \(progress.progressPercentage)")
        )
    }

    // MARK: - Header

    private var headerView: some View {
        HStack {
            Image(systemName: statusIcon)
                .foregroundStyle(statusColor)
            RFText(progress.fileName, style: .bodyBold)
                .lineLimit(1)
            Spacer()
            if progress.isCompleted {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(RFColors.success)
            }
        }
    }

    private var statusIcon: String {
        if progress.error != nil {
            return "exclamationmark.triangle.fill"
        } else if progress.isCompleted {
            return "doc.fill"
        } else {
            return "arrow.up.doc.fill"
        }
    }

    private var statusColor: Color {
        if progress.error != nil {
            return RFColors.error
        } else if progress.isCompleted {
            return RFColors.success
        } else {
            return RFColors.fallbackPrimary
        }
    }

    // MARK: - Progress Bar

    private var progressBarView: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 4)
                    .fill(RFColors.fallbackSurface)
                    .frame(height: 8)

                RoundedRectangle(cornerRadius: 4)
                    .fill(progressBarColor)
                    .frame(
                        width: max(0, geometry.size.width * progress.progress),
                        height: 8
                    )
                    .animation(.easeInOut(duration: 0.3), value: progress.progress)
            }
        }
        .frame(height: 8)
    }

    private var progressBarColor: Color {
        if progress.error != nil {
            return RFColors.error
        } else if progress.isCompleted {
            return RFColors.success
        } else {
            return RFColors.fallbackPrimary
        }
    }

    // MARK: - Detail

    private var detailView: some View {
        HStack {
            RFText(formattedUploadedSize, style: .caption)
            Spacer()
            if progress.error == nil {
                RFText("\(progress.progressPercentage)%", style: .captionBold)
            } else {
                RFText(progress.error ?? "", style: .caption)
                    .foregroundStyle(RFColors.error)
            }
        }
    }

    private var formattedUploadedSize: String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        let uploaded = formatter.string(fromByteCount: progress.uploadedBytes)
        let total = formatter.string(fromByteCount: progress.totalBytes)
        return "\(uploaded) / \(total)"
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFUploadProgressView(
            progress: FileUploadProgress(
                fileId: "1",
                fileName: "rapor.pdf",
                totalBytes: 2_500_000,
                uploadedBytes: 1_250_000,
                progress: 0.5,
                isCompleted: false,
                error: nil
            )
        )

        RFUploadProgressView(
            progress: FileUploadProgress(
                fileId: "2",
                fileName: "screenshot.png",
                totalBytes: 450_000,
                uploadedBytes: 450_000,
                progress: 1.0,
                isCompleted: true,
                error: nil
            )
        )

        RFUploadProgressView(
            progress: FileUploadProgress(
                fileId: "3",
                fileName: "cok-buyuk.zip",
                totalBytes: 100_000_000,
                uploadedBytes: 0,
                progress: 0.0,
                isCompleted: false,
                error: "Dosya boyutu cok buyuk"
            )
        )
    }
    .padding()
}
