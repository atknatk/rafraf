import Foundation
import Testing
@testable import RafRaf

/// FileMapper testleri.
@Suite("FileMapper Tests")
struct FileMapperTests {

    // MARK: - Upload Response Mapping

    @Test("Upload response DTO'yu domain modeline donusturmeli")
    func toDomainFromUploadResponse() {
        let dto = FileTestFactory.createUploadResponseDTO(
            fileKey: "projects/123/rapor.pdf"
        )

        let result = FileMapper.toDomain(
            from: dto,
            fileName: "rapor.pdf",
            contentType: "application/pdf",
            fileSize: 2_500_000
        )

        #expect(result.name == "rapor.pdf")
        #expect(result.fileKey == "projects/123/rapor.pdf")
        #expect(result.contentType == "application/pdf")
        #expect(result.size == 2_500_000)
        #expect(result.downloadURL == nil)
        #expect(result.localURL == nil)
        #expect(!result.id.isEmpty)
    }

    // MARK: - Download Response Mapping

    @Test("Download response DTO'yu domain modeline donusturmeli")
    func toDomainFromDownloadResponse() {
        let dto = FileTestFactory.createDownloadResponseDTO(
            downloadUrl: "https://s3.amazonaws.com/bucket/key",
            fileKey: "projects/123/screenshot.png"
        )
        let localURL = URL(fileURLWithPath: "/tmp/screenshot.png")

        let result = FileMapper.toDomain(from: dto, localURL: localURL)

        #expect(result.name == "screenshot.png")
        #expect(result.fileKey == "projects/123/screenshot.png")
        #expect(result.localURL == localURL)
        #expect(result.downloadURL != nil)
        #expect(!result.id.isEmpty)
    }

    @Test("Download mapping dosya adini file key'den cikarmali")
    func toDomainExtractsFileName() {
        let dto = FileTestFactory.createDownloadResponseDTO(
            fileKey: "projects/abc/nested/path/document.pdf"
        )
        let localURL = URL(fileURLWithPath: "/tmp/document.pdf")

        let result = FileMapper.toDomain(from: dto, localURL: localURL)

        #expect(result.name == "document.pdf")
    }
}
