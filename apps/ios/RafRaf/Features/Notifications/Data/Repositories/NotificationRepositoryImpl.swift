import Foundation
import os

/// Bildirim repository implementasyonu.
/// NetworkClient uzerinden backend API'sine erisir.
final class NotificationRepositoryImpl: NotificationRepositoryProtocol, @unchecked Sendable {

    private let networkClient: NetworkClient
    private let logger = AppLogger.logger(for: "NotificationRepository")

    init(networkClient: NetworkClient) {
        self.networkClient = networkClient
    }

    func registerDeviceToken(_ token: String) async throws -> DeviceTokenRegistration {
        logger.info("Device token kaydediliyor")
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
        let request = DeviceTokenRegisterRequestDTO(
            token: token,
            platform: "ios",
            appVersion: version
        )
        let response: DeviceTokenRegisterResponseDTO = try await networkClient.post(
            path: "/notifications/device-token",
            body: request
        )
        return NotificationMapper.toDomain(response)
    }

    func deleteDeviceToken(_ token: String) async throws {
        logger.info("Device token siliniyor")
        let request = DeviceTokenDeleteRequestDTO(token: token)
        let _: DeviceTokenRegisterResponseDTO? = try? await networkClient.post(
            path: "/notifications/device-token",
            body: request
        )
        // 204 No Content — no response body expected
    }

    func getNotificationSettings() async throws -> NotificationPreferences {
        logger.info("Bildirim ayarlari getiriliyor")
        let response: NotificationSettingsDTO = try await networkClient.get(
            path: "/notifications/settings"
        )
        return NotificationMapper.toDomain(response)
    }

    func updateNotificationSettings(
        _ preferences: NotificationPreferencesUpdate
    ) async throws -> NotificationPreferences {
        logger.info("Bildirim ayarlari guncelleniyor")
        let dto = NotificationMapper.toDTO(preferences)
        let response: NotificationSettingsDTO = try await networkClient.post(
            path: "/notifications/settings",
            body: dto
        )
        return NotificationMapper.toDomain(response)
    }
}
