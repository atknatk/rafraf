import Foundation

/// APNs device token'ini backend'e kaydeden use case.
struct RegisterDeviceTokenUseCase: Sendable {
    private let repository: NotificationRepositoryProtocol

    init(repository: NotificationRepositoryProtocol) {
        self.repository = repository
    }

    /// Device token'i kaydeder.
    /// - Parameter token: APNs device token string'i.
    /// - Returns: Kayit bilgisi.
    func execute(token: String) async throws -> DeviceTokenRegistration {
        try await repository.registerDeviceToken(token)
    }
}
