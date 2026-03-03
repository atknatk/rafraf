import Foundation

/// Device token kayit istegi DTO.
struct DeviceTokenRegisterRequestDTO: Codable, Sendable {
    let token: String
    let platform: String
    let appVersion: String?

    init(token: String, platform: String = "ios", appVersion: String? = nil) {
        self.token = token
        self.platform = platform
        self.appVersion = appVersion
    }
}

/// Device token kayit cevabi DTO.
struct DeviceTokenRegisterResponseDTO: Codable, Sendable {
    let id: UUID
    let registeredAt: Date
}

/// Device token silme istegi DTO.
struct DeviceTokenDeleteRequestDTO: Codable, Sendable {
    let token: String
}
