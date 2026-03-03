import Foundation
import Testing
@testable import RafRaf

/// SupportedFileType testleri.
@Suite("SupportedFileType Tests")
struct SupportedFileTypeTests {

    // MARK: - Max Size

    @Test("PDF max boyutu 20MB olmali")
    func pdfMaxSize() {
        #expect(SupportedFileType.pdf.maxSizeBytes == 20 * 1_024 * 1_024)
    }

    @Test("Image max boyutu 10MB olmali")
    func imageMaxSize() {
        #expect(SupportedFileType.image.maxSizeBytes == 10 * 1_024 * 1_024)
    }

    @Test("Text max boyutu 5MB olmali")
    func textMaxSize() {
        #expect(SupportedFileType.text.maxSizeBytes == 5 * 1_024 * 1_024)
    }

    @Test("Code max boyutu 5MB olmali")
    func codeMaxSize() {
        #expect(SupportedFileType.code.maxSizeBytes == 5 * 1_024 * 1_024)
    }

    @Test("Archive max boyutu 50MB olmali")
    func archiveMaxSize() {
        #expect(SupportedFileType.archive.maxSizeBytes == 50 * 1_024 * 1_024)
    }

    @Test("Global max boyut 50MB olmali")
    func globalMaxSize() {
        #expect(SupportedFileType.globalMaxSizeBytes == 50 * 1_024 * 1_024)
    }

    // MARK: - Extension Detection

    @Test("PDF uzantisi dogru tespit edilmeli")
    func fromExtensionPdf() {
        #expect(SupportedFileType.from(extension: "pdf") == .pdf)
    }

    @Test("PNG uzantisi image olarak tespit edilmeli")
    func fromExtensionPng() {
        #expect(SupportedFileType.from(extension: "png") == .image)
    }

    @Test("JPG uzantisi image olarak tespit edilmeli")
    func fromExtensionJpg() {
        #expect(SupportedFileType.from(extension: "jpg") == .image)
    }

    @Test("Swift uzantisi code olarak tespit edilmeli")
    func fromExtensionSwift() {
        #expect(SupportedFileType.from(extension: "swift") == .code)
    }

    @Test("ZIP uzantisi archive olarak tespit edilmeli")
    func fromExtensionZip() {
        #expect(SupportedFileType.from(extension: "zip") == .archive)
    }

    @Test("Bilinmeyen uzanti nil donmeli")
    func fromExtensionUnknown() {
        #expect(SupportedFileType.from(extension: "xyz") == nil)
    }

    @Test("Buyuk harfli uzanti da calismali")
    func fromExtensionUppercase() {
        #expect(SupportedFileType.from(extension: "PDF") == .pdf)
    }

    // MARK: - MIME Type Detection

    @Test("application/pdf MIME tipi pdf olarak tespit edilmeli")
    func fromMimeTypePdf() {
        #expect(SupportedFileType.from(mimeType: "application/pdf") == .pdf)
    }

    @Test("image/png MIME tipi image olarak tespit edilmeli")
    func fromMimeTypePng() {
        #expect(SupportedFileType.from(mimeType: "image/png") == .image)
    }

    // MARK: - Validation

    @Test("Gecerli dosya dogrulamadan gecmeli")
    func validateValidFile() {
        let result = SupportedFileType.validate(fileSize: 1_000_000, extension: "pdf")
        #expect(result == .success(.pdf))
    }

    @Test("Cok buyuk dosya reddedilmeli")
    func validateFileTooLarge() {
        let result = SupportedFileType.validate(
            fileSize: 60_000_000,
            extension: "zip"
        )
        #expect(result == .failure(.fileTooLarge(maxBytes: SupportedFileType.globalMaxSizeBytes)))
    }

    @Test("Desteklenmeyen uzanti reddedilmeli")
    func validateUnsupportedExtension() {
        let result = SupportedFileType.validate(fileSize: 1000, extension: "exe")
        #expect(result == .failure(.unsupportedType(extension: "exe")))
    }

    @Test("Tur bazli boyut limiti asimi reddedilmeli")
    func validateFileTooLargeForType() {
        let result = SupportedFileType.validate(
            fileSize: 25_000_000,  // 25MB, PDF limit 20MB
            extension: "pdf"
        )
        #expect(result == .failure(.fileTooLargeForType(
            type: .pdf,
            maxBytes: SupportedFileType.pdf.maxSizeBytes
        )))
    }

    // MARK: - Allowed Extensions

    @Test("PDF izin verilen uzantilar dogru olmali")
    func pdfAllowedExtensions() {
        #expect(SupportedFileType.pdf.allowedExtensions == ["pdf"])
    }

    @Test("Image izin verilen uzantilar dogru olmali")
    func imageAllowedExtensions() {
        #expect(SupportedFileType.image.allowedExtensions == ["png", "jpg", "jpeg", "gif"])
    }
}
