import Foundation
import os

/// Dosya secme ve yukleme ViewModel.
/// Dosya secimi, dogrulama, upload progress ve hata yonetimini saglar.
@Observable
@MainActor
final class FilePickerViewModel {
    // MARK: - State

    /// Secilen dosyanin yukleme ilerleme durumu.
    var uploadProgress: FileUploadProgress?
    /// Yukleme tamamlandi mi.
    var isUploadCompleted: Bool = false
    /// Yukleme devam ediyor mu.
    var isUploading: Bool = false
    /// Dosya secici acik mi.
    var isPickerPresented: Bool = false
    /// Hata mesaji.
    var errorMessage: String?
    /// Son yuklenen dosya.
    var uploadedFile: SharedFile?
    /// Indirilen dosya (onizleme icin).
    var downloadedFile: SharedFile?
    /// Indirme devam ediyor mu.
    var isDownloading: Bool = false
    /// Dosya onizleme gorunur mu.
    var isPreviewPresented: Bool = false

    // MARK: - Private

    private let uploadFileUseCase: UploadFileUseCase
    private let downloadFileUseCase: DownloadFileUseCase
    private let logger = AppLogger.logger(for: "FileSharing")

    // MARK: - Init

    init(
        uploadFileUseCase: UploadFileUseCase,
        downloadFileUseCase: DownloadFileUseCase
    ) {
        self.uploadFileUseCase = uploadFileUseCase
        self.downloadFileUseCase = downloadFileUseCase
    }

    // MARK: - Actions

    /// Dosya secicisini acar.
    func presentPicker() {
        isPickerPresented = true
    }

    /// Secilen dosyayi yukler.
    /// - Parameters:
    ///   - fileURL: Secilen dosyanin lokal URL'si.
    ///   - projectId: Proje ID'si.
    func uploadFile(fileURL: URL, projectId: String) async {
        guard !isUploading else { return }

        // Security-scoped resource erisimi
        guard fileURL.startAccessingSecurityScopedResource() else {
            errorMessage = String(localized: "fileSharing.error.accessDenied")
            logger.error("Dosya erisimi reddedildi: \(fileURL.lastPathComponent)")
            return
        }
        defer { fileURL.stopAccessingSecurityScopedResource() }

        isUploading = true
        isUploadCompleted = false
        errorMessage = nil
        uploadedFile = nil

        let fileName = fileURL.lastPathComponent
        let fileId = UUID().uuidString

        // Dosya boyutunu al
        let fileSize: Int64
        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: fileURL.path)
            fileSize = (attributes[.size] as? Int64) ?? 0
        } catch {
            errorMessage = String(localized: "fileSharing.error.fileReadFailed")
            isUploading = false
            logger.error("Dosya boyutu alinamadi: \(error.localizedDescription)")
            return
        }

        // Baslangic ilerleme
        uploadProgress = FileUploadProgress(
            fileId: fileId,
            fileName: fileName,
            totalBytes: fileSize,
            uploadedBytes: 0,
            progress: 0.0,
            isCompleted: false,
            error: nil
        )

        do {
            let result = try await uploadFileUseCase.execute(
                fileURL: fileURL,
                projectId: projectId,
                onProgress: { [weak self] progress in
                    Task { @MainActor [weak self] in
                        self?.uploadProgress = FileUploadProgress(
                            fileId: fileId,
                            fileName: fileName,
                            totalBytes: fileSize,
                            uploadedBytes: Int64(Double(fileSize) * progress),
                            progress: progress,
                            isCompleted: progress >= 1.0,
                            error: nil
                        )
                    }
                }
            )

            uploadedFile = result
            isUploadCompleted = true
            uploadProgress = FileUploadProgress(
                fileId: fileId,
                fileName: fileName,
                totalBytes: fileSize,
                uploadedBytes: fileSize,
                progress: 1.0,
                isCompleted: true,
                error: nil
            )
            logger.info("Dosya basariyla yuklendi: \(fileName)")
        } catch let error as FileValidationError {
            let message = validationErrorMessage(error)
            errorMessage = message
            uploadProgress = FileUploadProgress(
                fileId: fileId,
                fileName: fileName,
                totalBytes: fileSize,
                uploadedBytes: 0,
                progress: 0.0,
                isCompleted: false,
                error: message
            )
            logger.error("Dosya dogrulama hatasi: \(message)")
        } catch {
            let message = String(localized: "fileSharing.error.uploadFailed")
            errorMessage = message
            uploadProgress = FileUploadProgress(
                fileId: fileId,
                fileName: fileName,
                totalBytes: fileSize,
                uploadedBytes: 0,
                progress: 0.0,
                isCompleted: false,
                error: message
            )
            logger.error("Dosya yukleme hatasi: \(error.localizedDescription)")
        }

        isUploading = false
    }

    /// Dosyayi indirir ve onizleme icin hazirlar.
    /// - Parameters:
    ///   - projectId: Proje ID'si.
    ///   - fileKey: S3 object key.
    func downloadAndPreview(projectId: String, fileKey: String) async {
        guard !isDownloading else { return }

        isDownloading = true
        errorMessage = nil
        downloadedFile = nil

        do {
            let file = try await downloadFileUseCase.execute(
                projectId: projectId,
                fileKey: fileKey
            )
            downloadedFile = file
            isPreviewPresented = true
            logger.info("Dosya basariyla indirildi: \(file.name)")
        } catch {
            errorMessage = String(localized: "fileSharing.error.downloadFailed")
            logger.error("Dosya indirme hatasi: \(error.localizedDescription)")
        }

        isDownloading = false
    }

    /// Upload state'i sifirlar.
    func resetUploadState() {
        uploadProgress = nil
        isUploadCompleted = false
        isUploading = false
        errorMessage = nil
        uploadedFile = nil
    }

    // MARK: - Private

    private func validationErrorMessage(_ error: FileValidationError) -> String {
        switch error {
        case .fileTooLarge(let maxBytes):
            let maxMB = maxBytes / (1_024 * 1_024)
            return String(localized: "fileSharing.error.fileTooLarge \(maxMB)")
        case .unsupportedType(let ext):
            return String(localized: "fileSharing.error.unsupportedType \(ext)")
        case .fileTooLargeForType(let type, let maxBytes):
            let maxMB = maxBytes / (1_024 * 1_024)
            return String(localized: "fileSharing.error.fileTooLargeForType \(type.rawValue) \(maxMB)")
        }
    }
}
