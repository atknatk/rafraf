import Foundation

/// Session AI baslik guncellemelerini observe eden repository protokolu.
///
/// WebSocket'ten gelen `session.title` mesajlari `Data` katmaninda alinip
/// `SessionTitleUpdate`'e map edilir ve bu protokol uzerinden domain'e
/// stream edilir.
protocol SessionTitleRepositoryProtocol: Sendable {
    /// Yeni session baslik guncellemelerini emit eden async stream.
    /// Birden fazla observer ayni stream'i ortak olarak okur (broadcast).
    func titleUpdates() -> AsyncStream<SessionTitleUpdate>

    /// En son alinan baslik guncellemelerinin in-memory cache'i.
    /// Subscribe oncesi kacirilan event'leri replay etmek icin kullanilir.
    /// Anahtar: `sessionId`.
    func snapshot() async -> [String: SessionTitleUpdate]
}
