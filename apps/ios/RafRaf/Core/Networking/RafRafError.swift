import Foundation

/// Uygulama genelinde kullanilan hata tipleri.
enum RafRafError: Error, Sendable {
    case networkError
    case decodingError
    case unauthorized
    case notFound
    case serverError(String)
    case unknown(String)
}
