import Factory
import Foundation

/// Uygulama genelinde dependency injection container.
/// Factory kutuphanesi ile tum servislerin kaydi burada yapilir.
extension Container {

    /// Ag istemcisi.
    var networkClient: Factory<NetworkClient> {
        self { NetworkClient() }
            .singleton
    }

    /// WebSocket mesaj yonlendiricisi.
    var webSocketMessageRouter: Factory<WebSocketMessageRouter> {
        self { WebSocketMessageRouter() }
            .singleton
    }

    /// WebSocket istemcisi.
    var webSocketClient: Factory<WebSocketClient> {
        self { WebSocketClient(messageRouter: self.webSocketMessageRouter()) }
            .singleton
    }

    /// WebSocket baglanti yoneticisi.
    var webSocketConnectionManager: Factory<WebSocketConnectionManager> {
        self { @MainActor in WebSocketConnectionManager(webSocketClient: self.webSocketClient()) }
            .singleton
    }
}
