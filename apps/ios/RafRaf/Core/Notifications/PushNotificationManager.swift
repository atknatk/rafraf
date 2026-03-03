import Foundation
import os
import UserNotifications

/// APNs push bildirim yonetimi.
/// Token kaydi, izin isteme ve bildirim ayarlari.
@Observable
@MainActor
final class PushNotificationManager: NSObject {

    // MARK: - State

    /// Bildirim izni durumu.
    var authorizationStatus: UNAuthorizationStatus = .notDetermined

    /// Son kaydedilen APNs device token.
    var deviceToken: String?

    /// Gelen son bildirim (in-app gosterim icin).
    var latestNotification: PushNotification?

    /// Banner gosteriliyor mu.
    var isShowingBanner: Bool = false

    // MARK: - Private

    private let handleNotificationUseCase = HandleNotificationUseCase()
    private let logger = AppLogger.logger(for: "PushNotification")

    // MARK: - Public API

    /// Bildirim izni ister ve APNs kaydini baslatir.
    func requestAuthorization() async {
        let center = UNUserNotificationCenter.current()
        do {
            let granted = try await center.requestAuthorization(
                options: [.alert, .badge, .sound]
            )
            if granted {
                logger.info("Bildirim izni verildi")
                await registerForRemoteNotifications()
            } else {
                logger.info("Bildirim izni reddedildi")
            }
            await refreshAuthorizationStatus()
        } catch {
            logger.error("Bildirim izni hatasi: \(error.localizedDescription)")
        }
    }

    /// Mevcut izin durumunu kontrol eder.
    func refreshAuthorizationStatus() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        authorizationStatus = settings.authorizationStatus
    }

    /// APNs icin remote notification kaydini baslatir.
    func registerForRemoteNotifications() async {
        await MainActor.run {
            UIApplication.shared.registerForRemoteNotifications()
        }
        logger.info("Remote notification kaydi baslatildi")
    }

    /// APNs device token'i kaydeder.
    /// - Parameter tokenData: APNs tarafindan saglanan token verisi.
    func didRegisterForRemoteNotifications(deviceToken tokenData: Data) {
        let token = tokenData.map { String(format: "%02.2hhx", $0) }.joined()
        self.deviceToken = token
        logger.info("APNs token alindi: \(token.prefix(8))...")
    }

    /// APNs kayit hatasi.
    /// - Parameter error: Kayit sirasinda olusan hata.
    func didFailToRegisterForRemoteNotifications(error: Error) {
        logger.error("APNs kayit hatasi: \(error.localizedDescription)")
    }

    /// Gelen push bildirimi isler.
    /// - Parameter userInfo: Bildirim payload'i.
    func handleReceivedNotification(userInfo: [AnyHashable: Any]) {
        let stringKeyedInfo = userInfo.reduce(into: [String: Any]()) { result, pair in
            if let key = pair.key as? String {
                result[key] = pair.value
            }
        }

        guard let notification = handleNotificationUseCase.execute(
            userInfo: stringKeyedInfo
        ) else {
            logger.warning("Gecersiz bildirim payload'i")
            return
        }

        latestNotification = notification
        isShowingBanner = true
        logger.info(
            "Bildirim alindi: \(notification.category.rawValue) - \(notification.title)"
        )

        // Badge guncelle
        UNUserNotificationCenter.current().setBadgeCount(notification.badgeCount) { error in
            if let error {
                self.logger.error("Badge guncelleme hatasi: \(error.localizedDescription)")
            }
        }
    }

    /// Badge sayisini sifirlar (uygulama on plana geldiginde).
    func clearBadge() {
        UNUserNotificationCenter.current().setBadgeCount(0) { error in
            if let error {
                self.logger.error("Badge sifirlama hatasi: \(error.localizedDescription)")
            }
        }
    }

    /// Banner'i kapatir.
    func dismissBanner() {
        isShowingBanner = false
    }
}
