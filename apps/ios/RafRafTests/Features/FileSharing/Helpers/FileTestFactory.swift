import Foundation
@testable import RafRaf

/// FileSharing test data factory.
enum FileTestFactory {
    static func createSharedFile(
        id: String = "test-file-id",
        name: String = "rapor.pdf",
        fileKey: String = "projects/123/rapor.pdf",
        contentType: String = "application/pdf",
        size: Int = 2_500_000,
        downloadURL: URL? = nil,
        localURL: URL? = nil
    ) -> SharedFile {
        SharedFile(
            id: id,
            name: name,
            fileKey: fileKey,
            contentType: contentType,
            size: size,
            downloadURL: downloadURL,
            localURL: localURL
        )
    }

    static func createUploadProgress(
        fileId: String = "test-file-id",
        fileName: String = "rapor.pdf",
        totalBytes: Int64 = 2_500_000,
        uploadedBytes: Int64 = 1_250_000,
        progress: Double = 0.5,
        isCompleted: Bool = false,
        error: String? = nil
    ) -> FileUploadProgress {
        FileUploadProgress(
            fileId: fileId,
            fileName: fileName,
            totalBytes: totalBytes,
            uploadedBytes: uploadedBytes,
            progress: progress,
            isCompleted: isCompleted,
            error: error
        )
    }

    static func createUploadResponseDTO(
        uploadUrl: String = "https://s3.amazonaws.com/bucket/key",
        fileKey: String = "projects/123/rapor.pdf",
        expirationSeconds: Int = 3600
    ) -> FileUploadResponseDTO {
        FileUploadResponseDTO(
            uploadUrl: uploadUrl,
            fileKey: fileKey,
            expirationSeconds: expirationSeconds
        )
    }

    static func createDownloadResponseDTO(
        downloadUrl: String = "https://s3.amazonaws.com/bucket/key",
        fileKey: String = "projects/123/rapor.pdf",
        expirationSeconds: Int = 3600
    ) -> FileDownloadResponseDTO {
        FileDownloadResponseDTO(
            downloadUrl: downloadUrl,
            fileKey: fileKey,
            expirationSeconds: expirationSeconds
        )
    }
}
