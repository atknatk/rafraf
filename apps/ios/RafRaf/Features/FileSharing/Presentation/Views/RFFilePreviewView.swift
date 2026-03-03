import QuickLook
import SwiftUI

/// QuickLook dosya onizleme gorunumu.
/// PDF, resim, metin ve kod dosyalarini goruntuleme destegi.
struct RFFilePreviewView: View {
    let file: SharedFile
    let onDismiss: () -> Void

    var body: some View {
        NavigationStack {
            Group {
                if let localURL = file.localURL {
                    QuickLookPreviewRepresentable(url: localURL)
                } else {
                    RFErrorView(
                        message: String(localized: "fileSharing.preview.noLocalFile")
                    )
                }
            }
            .navigationTitle(file.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    RFButton(
                        String(localized: "fileSharing.preview.close"),
                        style: .ghost,
                        size: .small
                    ) {
                        onDismiss()
                    }
                }
            }
        }
        .accessibilityLabel(
            String(localized: "fileSharing.preview.accessibilityLabel \(file.name)")
        )
    }
}

// MARK: - QuickLook Representable

/// QLPreviewController SwiftUI wrapper.
struct QuickLookPreviewRepresentable: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> QLPreviewController {
        let controller = QLPreviewController()
        controller.dataSource = context.coordinator
        return controller
    }

    func updateUIViewController(
        _ uiViewController: QLPreviewController,
        context: Context
    ) {
        uiViewController.reloadData()
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(url: url)
    }

    final class Coordinator: NSObject, QLPreviewControllerDataSource {
        let url: URL

        init(url: URL) {
            self.url = url
        }

        func numberOfPreviewItems(
            in controller: QLPreviewController
        ) -> Int {
            1
        }

        func previewController(
            _ controller: QLPreviewController,
            previewItemAt index: Int
        ) -> QLPreviewItem {
            url as QLPreviewItem
        }
    }
}

#Preview {
    RFFilePreviewView(
        file: SharedFile(
            id: "preview",
            name: "ornek.pdf",
            fileKey: "projects/123/ornek.pdf",
            contentType: "application/pdf",
            size: 1_000_000,
            downloadURL: nil,
            localURL: nil
        ),
        onDismiss: {}
    )
}
