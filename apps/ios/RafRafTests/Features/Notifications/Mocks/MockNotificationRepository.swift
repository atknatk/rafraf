import Foundation
@testable import RafRaf

/// Test icin mock notification repository.
final class MockNotificationRepository: NotificationRepositoryProtocol, @unchecked Sendable {
    var registerCallCount = 0
    var deleteCallCount = 0
    var getSettingsCallCount = 0
    var updateSettingsCallCount = 0

    var lastRegisteredToken: String?
    var lastDeletedToken: String?
    var lastUpdateRequest: NotificationPreferencesUpdate?

    var registerResult: DeviceTokenRegistration?
    var registerError: Error?
    var deleteError: Error?
    var settingsResult: NotificationPreferences = NotificationPreferences(
        taskCompleteEnabled: true,
        approvalNeededEnabled: true,
        errorEnabled: true,
        infoEnabled: true
    )
    var settingsError: Error?
    var updateResult: NotificationPreferences = NotificationPreferences(
        taskCompleteEnabled: true,
        approvalNeededEnabled: true,
        errorEnabled: true,
        infoEnabled: true
    )
    var updateError: Error?

    func registerDeviceToken(_ token: String) async throws -> DeviceTokenRegistration {
        registerCallCount += 1
        lastRegisteredToken = token
        if let error = registerError { throw error }
        return registerResult ?? DeviceTokenRegistration(
            id: UUID(),
            registeredAt: Date()
        )
    }

    func deleteDeviceToken(_ token: String) async throws {
        deleteCallCount += 1
        lastDeletedToken = token
        if let error = deleteError { throw error }
    }

    func getNotificationSettings() async throws -> NotificationPreferences {
        getSettingsCallCount += 1
        if let error = settingsError { throw error }
        return settingsResult
    }

    func updateNotificationSettings(
        _ preferences: NotificationPreferencesUpdate
    ) async throws -> NotificationPreferences {
        updateSettingsCallCount += 1
        lastUpdateRequest = preferences
        if let error = updateError { throw error }
        return updateResult
    }
}
