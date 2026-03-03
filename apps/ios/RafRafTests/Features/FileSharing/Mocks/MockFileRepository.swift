import Foundation
@testable import RafRaf

/// Test icin mock file repository.
final class MockFileRepository: FileRepositoryProtocol, @unchecked Sendable {
    var uploadResult: Result<SharedFile, Error> = .success(
        SharedFile(
            id: "mock-id",
            name: "test.pdf",
            fileKey: "projects/123/test.pdf",
            contentType: "application/pdf",
            size: 1000,
            downloadURL: nil,
            localURL: nil
        )
    )
    var downloadResult: Result<SharedFile, Error> = .success(
        SharedFile(
            id: "mock-id",
            name: "test.pdf",
            fileKey: "projects/123/test.pdf",
            contentType: "application/pdf",
            size: 1000,
            downloadURL: URL(string: "https://example.com/test.pdf"),
            localURL: URL(fileURLWithPath: "/tmp/test.pdf")
        )
    )

    var uploadCallCount = 0
    var downloadCallCount = 0
    var lastUploadFileName: String?
    var lastUploadProjectId: String?
    var lastDownloadFileKey: String?
    var lastDownloadProjectId: String?
    var lastProgressCallback: ((Double) -> Void)?

    func uploadFile(
        fileURL: URL,
        projectId: String,
        fileName: String,
        contentType: String,
        fileSize: Int,
        onProgress: @Sendable @escaping (Double) -> Void
    ) async throws -> SharedFile {
        uploadCallCount += 1
        lastUploadFileName = fileName
        lastUploadProjectId = projectId
        lastProgressCallback = onProgress
        onProgress(1.0)
        return try uploadResult.get()
    }

    func downloadFile(
        projectId: String,
        fileKey: String
    ) async throws -> SharedFile {
        downloadCallCount += 1
        lastDownloadProjectId = projectId
        lastDownloadFileKey = fileKey
        return try downloadResult.get()
    }
}
