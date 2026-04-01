import Factory
import os
import UIKit
import UserNotifications

/// Uygulama delegesi.
/// Push notification lifecycle yonetimi icin UIApplicationDelegate implementasyonu.
/// SwiftUI @main struct'i UIApplicationDelegateAdaptor ile bu class'i kullanir.
final class AppDelegate: NSObject, UIApplicationDelegate, @unchecked Sendable {

    @Injected(\.pushNotificationManager)
    private var pushNotificationManager: PushNotificationManager

    // MARK: - UIApplicationDelegate

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        #if DEBUG
        DebugSetup.injectKeysIfNeeded()
        #endif

        // Live Activity push token sender'i kur
        configureLiveActivityPushTokenSender()

        // Bildirim delegesini ayarla
        let delegate = NotificationDelegate(manager: pushNotificationManager)
        UNUserNotificationCenter.current().delegate = delegate
        // Delegate'i retain et
        Self.notificationDelegate = delegate
        return true
    }

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        Task { @MainActor in
            pushNotificationManager.didRegisterForRemoteNotifications(
                deviceToken: deviceToken
            )
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        Task { @MainActor in
            pushNotificationManager.didFailToRegisterForRemoteNotifications(error: error)
        }
    }

    // MARK: - Private

    /// Notification delegate referansini saklar (retain).
    private static var notificationDelegate: NotificationDelegate?

    /// LiveActivityManager'a push token backend gonderim closure'ini ayarlar.
    private func configureLiveActivityPushTokenSender() {
        let networkClient = Container.shared.networkClient()
        LiveActivityManager.shared.pushTokenSender = { @Sendable taskId, token in
            struct TokenBody: Encodable, Sendable {
                let pushToken: String
                // swiftlint:disable:next nesting
                enum CodingKeys: String, CodingKey {
                    case pushToken = "push_token"
                }
            }
            struct EmptyResponse: Decodable, Sendable {}
            do {
                let _: EmptyResponse = try await networkClient.patch(
                    path: "/api/v1/tasks/\(taskId)/live-activity",
                    body: TokenBody(pushToken: token)
                )
            } catch {
                // Push token gonderim hatasi task'i etkilememeli
                os_log(.error, "Failed to send live activity push token: %@", error.localizedDescription)
            }
        }
    }
}

/// UNUserNotificationCenterDelegate implementasyonu.
/// Ayri class olarak tanimlanir cunku UNUserNotificationCenterDelegate
/// nonisolated requirement'lara sahiptir ve @MainActor class ile uyumsuz olur.
private final class NotificationDelegate: NSObject, UNUserNotificationCenterDelegate, @unchecked Sendable {

    private let manager: PushNotificationManager

    init(manager: PushNotificationManager) {
        self.manager = manager
    }

    /// Uygulama on plandayken gelen bildirim.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (
            UNNotificationPresentationOptions
        ) -> Void
    ) {
        // userInfo [AnyHashable: Any] Sendable degil; ancak burada tek
        // thread'den MainActor'a guvenli transfer yapiyoruz.
        nonisolated(unsafe) let userInfo = notification.request.content.userInfo
        Task { @MainActor in
            manager.handleReceivedNotification(userInfo: userInfo)
        }
        // Uygulama on plandayken banner ve ses goster
        completionHandler([.banner, .sound])
    }

    /// Kullanici bildirime tikladiginda.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        // userInfo [AnyHashable: Any] Sendable degil; ancak burada tek
        // thread'den MainActor'a guvenli transfer yapiyoruz.
        nonisolated(unsafe) let userInfo = response.notification.request.content.userInfo
        Task { @MainActor in
            manager.handleReceivedNotification(userInfo: userInfo)
        }
        completionHandler()
    }
}
