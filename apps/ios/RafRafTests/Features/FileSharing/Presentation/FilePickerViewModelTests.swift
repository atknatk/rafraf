import Foundation
import Testing
@testable import RafRaf

/// FilePickerViewModel testleri.
@Suite("FilePickerViewModel Tests")
struct FilePickerViewModelTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT(
        repository: MockFileRepository = MockFileRepository()
    ) -> (FilePickerViewModel, MockFileRepository) {
        let viewModel = FilePickerViewModel(
            uploadFileUseCase: UploadFileUseCase(repository: repository),
            downloadFileUseCase: DownloadFileUseCase(repository: repository)
        )
        return (viewModel, repository)
    }

    // MARK: - Initial State

    @Test("Baslangic durumu dogru olmali")
    @MainActor
    func initialState() {
        let (viewModel, _) = makeSUT()

        #expect(viewModel.uploadProgress == nil)
        #expect(viewModel.isUploadCompleted == false)
        #expect(viewModel.isUploading == false)
        #expect(viewModel.isPickerPresented == false)
        #expect(viewModel.errorMessage == nil)
        #expect(viewModel.uploadedFile == nil)
        #expect(viewModel.downloadedFile == nil)
        #expect(viewModel.isDownloading == false)
        #expect(viewModel.isPreviewPresented == false)
    }

    // MARK: - Present Picker

    @Test("Picker acma isPickerPresented'i true yapmali")
    @MainActor
    func presentPicker() {
        let (viewModel, _) = makeSUT()

        viewModel.presentPicker()

        #expect(viewModel.isPickerPresented == true)
    }

    // MARK: - Reset State

    @Test("Upload state sifirlanmali")
    @MainActor
    func resetUploadState() {
        let (viewModel, _) = makeSUT()
        viewModel.isUploadCompleted = true
        viewModel.errorMessage = "test error"

        viewModel.resetUploadState()

        #expect(viewModel.uploadProgress == nil)
        #expect(viewModel.isUploadCompleted == false)
        #expect(viewModel.isUploading == false)
        #expect(viewModel.errorMessage == nil)
        #expect(viewModel.uploadedFile == nil)
    }

    // MARK: - Download

    @Test("Basarili indirme sonrasi onizleme acilmali")
    @MainActor
    func downloadAndPreviewSuccess() async {
        let expectedFile = FileTestFactory.createSharedFile(
            localURL: URL(fileURLWithPath: "/tmp/test.pdf")
        )
        let repo = MockFileRepository()
        repo.downloadResult = .success(expectedFile)
        let (viewModel, _) = makeSUT(repository: repo)

        await viewModel.downloadAndPreview(
            projectId: "123",
            fileKey: "projects/123/test.pdf"
        )

        #expect(viewModel.downloadedFile != nil)
        #expect(viewModel.isPreviewPresented == true)
        #expect(viewModel.isDownloading == false)
        #expect(viewModel.errorMessage == nil)
    }

    @Test("Basarisiz indirme hata mesaji gostermeli")
    @MainActor
    func downloadAndPreviewError() async {
        let repo = MockFileRepository()
        repo.downloadResult = .failure(FileRepositoryError.downloadFailed(statusCode: 500))
        let (viewModel, _) = makeSUT(repository: repo)

        await viewModel.downloadAndPreview(
            projectId: "123",
            fileKey: "projects/123/missing.pdf"
        )

        #expect(viewModel.downloadedFile == nil)
        #expect(viewModel.isPreviewPresented == false)
        #expect(viewModel.isDownloading == false)
        #expect(viewModel.errorMessage != nil)
    }
}
