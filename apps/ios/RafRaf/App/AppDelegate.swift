import Factory
import UIKit
import UserNotifications

/// Uygulama delegesi.
/// Push notification lifecycle yonetimi icin UIApplicationDelegate implementasyonu.
/// SwiftUI @main struct'i UIApplicationDelegateAdaptor ile bu class'i kullanir.
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    @Injected(\.pushNotificationManager)
    private var pushNotificationManager: PushNotificationManager

    // MARK: - UIApplicationDelegate

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // Bildirim delegesini ayarla
        UNUserNotificationCenter.current().delegate = self
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

    // MARK: - UNUserNotificationCenterDelegate

    /// Uygulama on plandayken gelen bildirim.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (
            UNNotificationPresentationOptions
        ) -> Void
    ) {
        let userInfo = notification.request.content.userInfo
        Task { @MainActor in
            pushNotificationManager.handleReceivedNotification(userInfo: userInfo)
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
        let userInfo = response.notification.request.content.userInfo
        Task { @MainActor in
            pushNotificationManager.handleReceivedNotification(userInfo: userInfo)
        }
        completionHandler()
    }
}
