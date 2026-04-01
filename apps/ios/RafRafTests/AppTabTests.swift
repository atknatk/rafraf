import Foundation
import Testing
@testable import RafRaf

/// AppTab ve tab navigation testleri.
@Suite("AppTab Tests")
struct AppTabTests {

    @Test("AppTab tum varyantlari mevcut olmali")
    func allTabsExist() {
        let tabs: [AppTab] = [.projects, .chat, .agents, .settings]
        #expect(tabs.count == 4)
    }

    @Test("AppTab projects rawValue dogru olmali")
    func projectsRawValue() {
        #expect(AppTab.projects.rawValue == "projects")
    }

    @Test("AppTab chat rawValue dogru olmali")
    func chatRawValue() {
        #expect(AppTab.chat.rawValue == "chat")
    }

    @Test("AppTab settings rawValue dogru olmali")
    func settingsRawValue() {
        #expect(AppTab.settings.rawValue == "settings")
    }

    @Test("AppTab Hashable uyumlu olmali")
    func tabHashable() {
        var set = Set<AppTab>()
        set.insert(.projects)
        set.insert(.chat)
        set.insert(.agents)
        set.insert(.settings)
        #expect(set.count == 4)
    }

    @Test("AppTab Sendable uyumlu olmali")
    func tabSendable() {
        let tab: any Sendable = AppTab.projects
        #expect(tab is AppTab)
    }
}
