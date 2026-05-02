import Foundation
import Testing
@testable import RafRaf

/// AppSettings domain model testleri.
@Suite("AppSettings Domain Model Tests")
struct AppSettingsModelTests {

    // MARK: - Defaults

    @Test("AppSettings varsayilan degerleri dogru olmali")
    func defaults() {
        let settings = AppSettings.defaults

        #expect(settings.pushNotificationsEnabled == true)
        #expect(settings.enabledNotificationTypes == Set(NotificationType.allCases))
        #expect(settings.appearance == .system)
        #expect(settings.fontSize == .medium)
    }

    // MARK: - Equatable

    @Test("AppSettings Equatable dogru calismali")
    func equatable() {
        let settings1 = AppSettings.defaults
        let settings2 = AppSettings.defaults

        #expect(settings1 == settings2)
    }

    @Test("AppSettings farkli degerlerle esit olmamali")
    func notEqual() {
        let settings1 = AppSettings.defaults
        var settings2 = AppSettings.defaults
        settings2.appearance = .dark

        #expect(settings1 != settings2)
    }

    // MARK: - AppAppearance

    @Test("AppAppearance tum case'leri dogru olmali")
    func appearanceCases() {
        let allCases = AppAppearance.allCases
        #expect(allCases.count == 3)
        #expect(allCases.contains(.system))
        #expect(allCases.contains(.light))
        #expect(allCases.contains(.dark))
    }

    @Test("AppAppearance rawValue dogru olmali")
    func appearanceRawValues() {
        #expect(AppAppearance.system.rawValue == "system")
        #expect(AppAppearance.light.rawValue == "light")
        #expect(AppAppearance.dark.rawValue == "dark")
    }

    @Test("AppAppearance localizedTitle bos olmamali")
    func appearanceLocalizedTitles() {
        for appearance in AppAppearance.allCases {
            #expect(!appearance.localizedTitle.isEmpty)
        }
    }

    // MARK: - AppFontSize

    @Test("AppFontSize tum case'leri dogru olmali")
    func fontSizeCases() {
        let allCases = AppFontSize.allCases
        #expect(allCases.count == 3)
        #expect(allCases.contains(.small))
        #expect(allCases.contains(.medium))
        #expect(allCases.contains(.large))
    }

    @Test("AppFontSize rawValue dogru olmali")
    func fontSizeRawValues() {
        #expect(AppFontSize.small.rawValue == "small")
        #expect(AppFontSize.medium.rawValue == "medium")
        #expect(AppFontSize.large.rawValue == "large")
    }

    @Test("AppFontSize dynamicTypeSize degerleri mantikli olmali")
    func fontSizeDynamicType() {
        #expect(AppFontSize.small.dynamicTypeSize < AppFontSize.medium.dynamicTypeSize)
        #expect(AppFontSize.medium.dynamicTypeSize < AppFontSize.large.dynamicTypeSize)
        #expect(AppFontSize.medium.dynamicTypeSize == 1.0)
    }

    @Test("AppFontSize localizedTitle bos olmamali")
    func fontSizeLocalizedTitles() {
        for size in AppFontSize.allCases {
            #expect(!size.localizedTitle.isEmpty)
        }
    }

    // MARK: - NotificationType

    @Test("NotificationType tum case'leri dogru olmali")
    func notificationTypeCases() {
        let allCases = NotificationType.allCases
        #expect(allCases.count == 3)
        #expect(allCases.contains(.taskUpdates))
        #expect(allCases.contains(.approvalRequests))
        #expect(allCases.contains(.systemAlerts))
    }

    @Test("NotificationType rawValue dogru olmali")
    func notificationTypeRawValues() {
        #expect(NotificationType.taskUpdates.rawValue == "taskUpdates")
        #expect(NotificationType.approvalRequests.rawValue == "approvalRequests")
        #expect(NotificationType.systemAlerts.rawValue == "systemAlerts")
    }

    @Test("NotificationType localizedTitle bos olmamali")
    func notificationTypeLocalizedTitles() {
        for type in NotificationType.allCases {
            #expect(!type.localizedTitle.isEmpty)
        }
    }

    // MARK: - Mutability

    @Test("AppSettings mutable olmali")
    func settingsMutable() {
        var settings = AppSettings.defaults
        settings.pushNotificationsEnabled = false
        settings.enabledNotificationTypes = [.taskUpdates]
        settings.appearance = .dark
        settings.fontSize = .large

        #expect(settings.pushNotificationsEnabled == false)
        #expect(settings.enabledNotificationTypes == [.taskUpdates])
        #expect(settings.appearance == .dark)
        #expect(settings.fontSize == .large)
    }
}
