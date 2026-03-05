import Foundation
import os

/// Dosya paylasimi repository implementasyonu.
/// NetworkClient ile pre-signed URL alir, URLSession ile S3 upload/download yapar.
final class FileRepositoryImpl: FileRepositoryProtocol, @unchecked Sendable {
    private let networkClient: NetworkClient
    private let logger = AppLogger.logger(for: "FileSharing")

    init(networkClient: NetworkClient) {
        self.networkClient = networkClient
    }

    func uploadFile(
        fileURL: URL,
        projectId: String,
        fileName: String,
        contentType: String,
        fileSize: Int,
        onProgress: @Sendable @escaping (Double) -> Void
    ) async throws -> SharedFile {
        logger.info("Dosya yukleme baslatiliyor: \(fileName)")

        // 1. Pre-signed upload URL al
        let requestDTO = FileUploadRequestDTO(
            projectId: projectId,
            fileName: fileName,
            contentType: contentType,
            fileSize: fileSize
        )

        let responseDTO: FileUploadResponseDTO = try await networkClient.post(
            path: "/files/upload-url",
            body: requestDTO
        )

        logger.info("Pre-signed URL alindi: \(responseDTO.fileKey)")

        // 2. Dosyayi S3'e yukle (URLSession ile)
        guard let uploadURL = URL(string: responseDTO.uploadUrl) else {
            throw FileRepositoryError.invalidURL
        }

        var request = URLRequest(url: uploadURL)
        request.httpMethod = "PUT"
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")

        let fileData = try Data(contentsOf: fileURL)

        // Upload with progress tracking via delegate
        let delegate = UploadProgressDelegate(onProgress: onProgress)
        let session = URLSession(
            configuration: .default,
            delegate: delegate,
            delegateQueue: nil
        )

        let (_, response) = try await session.upload(for: request, from: fileData)
        session.invalidateAndCancel()

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
            logger.error("S3 upload hatasi: status \(statusCode)")
            throw FileRepositoryError.uploadFailed(statusCode: statusCode)
        }

        onProgress(1.0)
        logger.info("Dosya basariyla yuklendi: \(responseDTO.fileKey)")

        return FileMapper.toDomain(
            from: responseDTO,
            fileName: fileName,
            contentType: contentType,
            fileSize: fileSize
        )
    }

    func downloadFile(
        projectId: String,
        fileKey: String
    ) async throws -> SharedFile {
        logger.info("Dosya indirme baslatiliyor: \(fileKey)")

        // 1. Pre-signed download URL al
        let requestDTO = FileDownloadRequestDTO(
            projectId: projectId,
            fileKey: fileKey
        )

        let responseDTO: FileDownloadResponseDTO = try await networkClient.post(
            path: "/files/download-url",
            body: requestDTO
        )

        logger.info("Download URL alindi: \(responseDTO.fileKey)")

        // 2. Dosyayi indir
        guard let downloadURL = URL(string: responseDTO.downloadUrl) else {
            throw FileRepositoryError.invalidURL
        }

        let (tempURL, response) = try await URLSession.shared.download(from: downloadURL)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
            logger.error("S3 download hatasi: status \(statusCode)")
            throw FileRepositoryError.downloadFailed(statusCode: statusCode)
        }

        // 3. Gecici dizine kaydet (QuickLook icin)
        let fileName = (fileKey as NSString).lastPathComponent
        let destinationURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent(fileName)

        try FileManager.default.createDirectory(
            at: destinationURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try FileManager.default.moveItem(at: tempURL, to: destinationURL)

        logger.info("Dosya basariyla indirildi: \(destinationURL.lastPathComponent)")

        return FileMapper.toDomain(
            from: responseDTO,
            localURL: destinationURL
        )
    }
}

/// Upload progress takibi icin URLSession delegate.
final class UploadProgressDelegate: NSObject, URLSessionTaskDelegate, Sendable {
    private let onProgress: @Sendable (Double) -> Void

    init(onProgress: @Sendable @escaping (Double) -> Void) {
        self.onProgress = onProgress
    }

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didSendBodyData bytesSent: Int64,
        totalBytesSent: Int64,
        totalBytesExpectedToSend: Int64
    ) {
        guard totalBytesExpectedToSend > 0 else { return }
        let progress = Double(totalBytesSent) / Double(totalBytesExpectedToSend)
        onProgress(progress)
    }
}

/// Dosya repository hatalari.
enum FileRepositoryError: Error, Sendable {
    case invalidURL
    case uploadFailed(statusCode: Int)
    case downloadFailed(statusCode: Int)
}
