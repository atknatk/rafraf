import SwiftUI
import UniformTypeIdentifiers

/// Dosya secici gorunumu.
/// UIDocumentPickerViewController ile dosya secmeyi saglar.
struct RFFilePickerView: View {
    @State private var viewModel: FilePickerViewModel
    let projectId: String

    init(viewModel: FilePickerViewModel, projectId: String) {
        self._viewModel = State(initialValue: viewModel)
        self.projectId = projectId
    }

    var body: some View {
        VStack(spacing: RFSpacing.md) {
            // Upload buton
            if !viewModel.isUploading {
                selectFileButton
            }

            // Upload ilerleme
            if let progress = viewModel.uploadProgress {
                RFUploadProgressView(progress: progress)
            }

            // Hata mesaji
            if let error = viewModel.errorMessage {
                RFText(error, style: .caption)
                    .foregroundStyle(RFColors.error)
            }

            // Yukleme tamamlandi
            if viewModel.isUploadCompleted, let file = viewModel.uploadedFile {
                RFFileAttachmentCard(
                    file: file,
                    isDownloading: false,
                    onTap: {}
                )
            }
        }
        .sheet(isPresented: $viewModel.isPickerPresented) {
            DocumentPickerRepresentable { url in
                Task {
                    await viewModel.uploadFile(fileURL: url, projectId: projectId)
                }
            }
        }
    }

    // MARK: - Select File Button

    private var selectFileButton: some View {
        RFButton(
            String(localized: "fileSharing.selectFile"),
            style: .outline,
            size: .medium
        ) {
            viewModel.presentPicker()
        }
    }
}

// MARK: - UIDocumentPicker Representable

/// UIDocumentPickerViewController SwiftUI wrapper.
/// Desteklenen dosya turlerini kabul eder.
struct DocumentPickerRepresentable: UIViewControllerRepresentable {
    let onDocumentPicked: (URL) -> Void

    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let supportedTypes: [UTType] = [
            .pdf,
            .png, .jpeg, .gif,
            .plainText,
            .sourceCode,
            .zip,
            .data,
        ]

        let picker = UIDocumentPickerViewController(
            forOpeningContentTypes: supportedTypes,
            asCopy: true
        )
        picker.delegate = context.coordinator
        picker.allowsMultipleSelection = false
        return picker
    }

    func updateUIViewController(
        _ uiViewController: UIDocumentPickerViewController,
        context: Context
    ) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onDocumentPicked: onDocumentPicked)
    }

    final class Coordinator: NSObject, UIDocumentPickerDelegate {
        let onDocumentPicked: (URL) -> Void

        init(onDocumentPicked: @escaping (URL) -> Void) {
            self.onDocumentPicked = onDocumentPicked
        }

        func documentPicker(
            _ controller: UIDocumentPickerViewController,
            didPickDocumentsAt urls: [URL]
        ) {
            guard let url = urls.first else { return }
            onDocumentPicked(url)
        }
    }
}

#Preview {
    RFFilePickerView(
        viewModel: FilePickerViewModel(
            uploadFileUseCase: UploadFileUseCase(
                repository: PreviewFileRepository()
            ),
            downloadFileUseCase: DownloadFileUseCase(
                repository: PreviewFileRepository()
            )
        ),
        projectId: "preview-project"
    )
    .padding()
}

/// Preview icin mock repository.
private struct PreviewFileRepository: FileRepositoryProtocol {
    func uploadFile(
        fileURL: URL,
        projectId: String,
        fileName: String,
        contentType: String,
        fileSize: Int,
        onProgress: @Sendable @escaping (Double) -> Void
    ) async throws -> SharedFile {
        SharedFile(
            id: "preview",
            name: fileName,
            fileKey: "projects/\(projectId)/\(fileName)",
            contentType: contentType,
            size: fileSize,
            downloadURL: nil,
            localURL: nil
        )
    }

    func downloadFile(
        projectId: String,
        fileKey: String
    ) async throws -> SharedFile {
        SharedFile(
            id: "preview",
            name: "preview.pdf",
            fileKey: fileKey,
            contentType: "application/pdf",
            size: 0,
            downloadURL: nil,
            localURL: nil
        )
    }
}
