import Foundation
import Testing
@testable import RafRaf

/// File DTO encode/decode testleri.
@Suite("File DTO Tests")
struct FileDTOTests {

    // MARK: - FileUploadRequestDTO

    @Test("FileUploadRequestDTO encode edilebilmeli")
    func uploadRequestEncoding() throws {
        let dto = FileUploadRequestDTO(
            projectId: "123e4567-e89b-12d3-a456-426614174000",
            fileName: "rapor.pdf",
            contentType: "application/pdf",
            fileSize: 2_500_000
        )

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(dto)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]

        #expect(json?["project_id"] as? String == "123e4567-e89b-12d3-a456-426614174000")
        #expect(json?["file_name"] as? String == "rapor.pdf")
        #expect(json?["content_type"] as? String == "application/pdf")
        #expect(json?["file_size"] as? Int == 2_500_000)
    }

    // MARK: - FileUploadResponseDTO

    @Test("FileUploadResponseDTO decode edilebilmeli")
    func uploadResponseDecoding() throws {
        let json = """
        {
            "upload_url": "https://s3.amazonaws.com/bucket/key?sig=abc",
            "file_key": "projects/123/rapor.pdf",
            "expiration_seconds": 3600
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let dto = try decoder.decode(FileUploadResponseDTO.self, from: json)

        #expect(dto.uploadUrl == "https://s3.amazonaws.com/bucket/key?sig=abc")
        #expect(dto.fileKey == "projects/123/rapor.pdf")
        #expect(dto.expirationSeconds == 3600)
    }

    // MARK: - FileDownloadResponseDTO

    @Test("FileDownloadResponseDTO decode edilebilmeli")
    func downloadResponseDecoding() throws {
        let json = """
        {
            "download_url": "https://s3.amazonaws.com/bucket/key?sig=xyz",
            "file_key": "projects/123/screenshot.png",
            "expiration_seconds": 3600
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let dto = try decoder.decode(FileDownloadResponseDTO.self, from: json)

        #expect(dto.downloadUrl == "https://s3.amazonaws.com/bucket/key?sig=xyz")
        #expect(dto.fileKey == "projects/123/screenshot.png")
        #expect(dto.expirationSeconds == 3600)
    }

    // MARK: - FileDownloadRequestDTO

    @Test("FileDownloadRequestDTO encode edilebilmeli")
    func downloadRequestEncoding() throws {
        let dto = FileDownloadRequestDTO(
            projectId: "123",
            fileKey: "projects/123/rapor.pdf"
        )

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(dto)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]

        #expect(json?["project_id"] as? String == "123")
        #expect(json?["file_key"] as? String == "projects/123/rapor.pdf")
    }
}
