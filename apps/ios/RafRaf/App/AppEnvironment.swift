import Foundation

/// Uygulama ortam konfigurasyonu.
/// Build konfigurasyonlarina gore API URL ve diger ayarlari saglar.
enum AppEnvironment: Sendable {
    case development
    case staging
    case production

    /// Aktif ortam.
    static var current: AppEnvironment {
        #if DEBUG
        return .development
        #else
        return .production
        #endif
    }

    /// Development backend host.
    /// Simulator: localhost, fiziksel cihaz: Mac'in lokal IP adresi.
    private static let devHost: String = {
        #if targetEnvironment(simulator)
        return "localhost"
        #else
        return "192.168.0.100"
        #endif
    }()

    /// Backend WebSocket URL.
    var webSocketURL: URL {
        switch self {
        case .development:
            guard let url = URL(string: "ws://\(Self.devHost):8000/ws") else {
                fatalError("Gecersiz development WebSocket URL")
            }
            return url
        case .staging:
            guard let url = URL(string: "wss://rafraf-api.everva.com.tr/ws") else {
                fatalError("Gecersiz staging WebSocket URL")
            }
            return url
        case .production:
            guard let url = URL(string: "wss://rafraf-api.everva.com.tr/ws") else {
                fatalError("Gecersiz production WebSocket URL")
            }
            return url
        }
    }

    /// Backend REST API base URL.
    var apiBaseURL: URL {
        switch self {
        case .development:
            guard let url = URL(string: "http://\(Self.devHost):8000/api/v1") else {
                fatalError("Gecersiz development API URL")
            }
            return url
        case .staging:
            guard let url = URL(string: "https://rafraf-api.everva.com.tr/api/v1") else {
                fatalError("Gecersiz staging API URL")
            }
            return url
        case .production:
            guard let url = URL(string: "https://rafraf-api.everva.com.tr/api/v1") else {
                fatalError("Gecersiz production API URL")
            }
            return url
        }
    }
}
