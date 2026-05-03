import Foundation

/// V1.x SHIP BLOCKER fix — application-layer ACK + retry kontrati.
///
/// `ApprovalRepositoryImpl`'in WebSocket gonderim katmanini soyutlar. Production
/// implementasyonu `WebSocketClient` etrafindaki bir adapter; testte
/// `MockApprovalDeliveryChannel` stale-connection senaryosunu uretir.
///
/// Bug ozeti (live e2e 2026-05-03): URLSession `send` TCP buffer'a yazilirken
/// success doner ama yarim-olu baglanti uzerinde mesaj kabloda kaybolabilir.
/// iOS bunu sadece heartbeat timeout ile (32s sonra) farkeder; bu surede
/// yapilan critical message gonderimleri SESSIZ KAYBOLUR.
///
/// Cozum kontrati:
/// - `send(envelope:clientMessageId:)` → wire formatinda gonderir; tum gonderim
///   hatalari throw edilir. Gonderim "yapildi" demek "teslim edildi" anlamina
///   GELMEZ — teslim onayi `awaitAck` ile beklenir.
/// - `awaitAck(clientMessageId:timeout:)` → backend tarafindan echo'lanan
///   `ack` envelope'i icin bekler. Timeout durumunda
///   `WebSocketError.deliveryTimeout` firlatir.
/// - `forceReconnect()` → mevcut WebSocket task'ini kapatir ve yeniden
///   baglantiyi tetikler. Repository sadece "elimdeki kanal yari-olu, baska
///   yol yok" durumunda cagirir; UI ek bir gosterge yapmaz (mevcut
///   reconnecting state UI'i yeterli).
protocol ApprovalDeliveryChannel: Sendable {

    /// JSON envelope'u gonderir. Hata durumunda `WebSocketError` firlatir.
    /// - Parameters:
    ///   - envelope: Wire-encoded JSON string (WebSocketBaseMessage encode'u).
    ///   - clientMessageId: Backend ack'inde echo'lanacak benzersiz id.
    func send(envelope: String, clientMessageId: String) async throws

    /// `clientMessageId` icin backend `ack` envelope'i bekler.
    /// - Parameters:
    ///   - clientMessageId: Bekleyen mesaj id'si.
    ///   - timeout: Maksimum bekleme suresi.
    /// - Throws: `WebSocketError.deliveryTimeout` timeout durumunda.
    func awaitAck(clientMessageId: String, timeout: Duration) async throws

    /// Mevcut baglantiyi sonlandirir ve reconnect tetikler. Reconnect
    /// TAMAMLANANA kadar (state `.connected`) bekler; aksi halde
    /// `WebSocketError.connectionFailed` firlatir. Repository bu hatayi
    /// `deliveryFailed`'e map eder. Idempotent: zaten reconnect ediyorsa
    /// sadece bekler, ek tetikleme yapmaz.
    func forceReconnect() async throws
}
