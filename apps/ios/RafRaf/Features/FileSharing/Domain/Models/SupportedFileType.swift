import Foundation

/// Desteklenen dosya turleri.
/// Her tur icin max boyut, izin verilen uzantilar ve MIME tipleri tanimlanir.
enum SupportedFileType: String, Sendable, CaseIterable {
    case pdf
    case image
    case text
    case code
    case log
    case archive

    /// Tur bazli maksimum dosya boyutu (bytes).
    var maxSizeBytes: Int {
        switch self {
        case .pdf: 20 * 1_024 * 1_024       // 20MB
        case .image: 10 * 1_024 * 1_024      // 10MB
        case .text: 5 * 1_024 * 1_024        // 5MB
        case .code: 5 * 1_024 * 1_024        // 5MB
        case .log: 10 * 1_024 * 1_024        // 10MB
        case .archive: 50 * 1_024 * 1_024    // 50MB
        }
    }

    /// Izin verilen dosya uzantilari.
    var allowedExtensions: [String] {
        switch self {
        case .pdf: ["pdf"]
        case .image: ["png", "jpg", "jpeg", "gif"]
        case .text: ["txt", "md"]
        case .code: ["py", "js", "ts", "swift"]
        case .log: ["log"]
        case .archive: ["zip"]
        }
    }

    /// Izin verilen MIME tipleri.
    var mimeTypes: [String] {
        switch self {
        case .pdf:
            ["application/pdf"]
        case .image:
            ["image/png", "image/jpeg", "image/gif"]
        case .text:
            ["text/plain", "text/markdown"]
        case .code:
            [
                "text/x-python", "text/javascript", "text/typescript",
                "text/x-swift", "application/x-python-code",
                "application/javascript",
            ]
        case .log:
            ["text/x-log", "text/plain"]
        case .archive:
            ["application/zip"]
        }
    }

    /// Global maksimum dosya boyutu (50MB).
    static let globalMaxSizeBytes: Int = 50 * 1_024 * 1_024

    /// Dosya uzantisindan dosya turunu belirler.
    /// - Parameter extension_: Dosya uzantisi (kucuk harfle).
    /// - Returns: Uygun dosya turu, bulunamazsa nil.
    static func from(extension extension_: String) -> SupportedFileType? {
        let ext = extension_.lowercased()
        return allCases.first { $0.allowedExtensions.contains(ext) }
    }

    /// MIME tipinden dosya turunu belirler.
    /// - Parameter mimeType: MIME tipi.
    /// - Returns: Uygun dosya turu, bulunamazsa nil.
    static func from(mimeType: String) -> SupportedFileType? {
        let mime = mimeType.lowercased()
        return allCases.first { $0.mimeTypes.contains(mime) }
    }

    /// Dosyayi dogrular: boyut ve tur kontrolu.
    /// - Parameters:
    ///   - fileSize: Dosya boyutu (bytes).
    ///   - extension_: Dosya uzantisi.
    /// - Returns: Dogrulama sonucu.
    static func validate(
        fileSize: Int,
        extension extension_: String
    ) -> FileValidationResult {
        guard fileSize <= globalMaxSizeBytes else {
            return .failure(.fileTooLarge(maxBytes: globalMaxSizeBytes))
        }

        guard let fileType = from(extension: extension_) else {
            return .failure(.unsupportedType(extension: extension_))
        }

        guard fileSize <= fileType.maxSizeBytes else {
            return .failure(.fileTooLargeForType(
                type: fileType,
                maxBytes: fileType.maxSizeBytes
            ))
        }

        return .success(fileType)
    }
}

/// Dosya dogrulama sonucu.
enum FileValidationResult: Sendable, Equatable {
    case success(SupportedFileType)
    case failure(FileValidationError)
}

/// Dosya dogrulama hatalari.
enum FileValidationError: Error, Sendable, Equatable {
    /// Dosya boyutu global limiti asiyor.
    case fileTooLarge(maxBytes: Int)
    /// Dosya turu desteklenmiyor.
    case unsupportedType(extension: String)
    /// Dosya boyutu tur bazli limiti asiyor.
    case fileTooLargeForType(type: SupportedFileType, maxBytes: Int)
}
