import Foundation

/// Voice input repository protokolu.
/// Domain katmani Data katmanindan izole kalir; bu protokol uzerinden iletisir.
protocol VoiceInputRepositoryProtocol: Sendable {
    /// Deepgram WebSocket baglantisi kurar ve ses streaming'i baslatir.
    /// - Parameter language: Transkripsiyon dili.
    /// - Returns: Transkripsiyon sonuclarini yayan AsyncStream.
    func startStreaming(language: VoiceLanguage) async throws -> AsyncStream<TranscriptionResult>

    /// Streaming'i durdurur ve baglantilari kapatir.
    func stopStreaming() async

    /// Deepgram baglantisi aktif mi?
    var isConnected: Bool { get }
}
