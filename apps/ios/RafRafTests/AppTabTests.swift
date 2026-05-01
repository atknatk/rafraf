import Foundation
import Testing
@testable import RafRaf

/// AppTab ve tab navigation testleri.
@Suite("AppTab Tests")
struct AppTabTests {

    @Test("AppTab tum varyantlari mevcut olmali")
    func allTabsExist() {
        let tabs: [AppTab] = [.home, .chat, .agents, .settings]
        #expect(tabs.count == 4)
    }

    @Test("AppTab home rawValue dogru olmali")
    func homeRawValue() {
        #expect(AppTab.home.rawValue == "home")
    }

    @Test("AppTab chat rawValue dogru olmali")
    func chatRawValue() {
        #expect(AppTab.chat.rawValue == "chat")
    }

    @Test("AppTab agents rawValue dogru olmali")
    func agentsRawValue() {
        #expect(AppTab.agents.rawValue == "agents")
    }

    @Test("AppTab settings rawValue dogru olmali")
    func settingsRawValue() {
        #expect(AppTab.settings.rawValue == "settings")
    }

    @Test("AppTab Hashable uyumlu olmali")
    func tabHashable() {
        var set = Set<AppTab>()
        set.insert(.home)
        set.insert(.chat)
        set.insert(.agents)
        set.insert(.settings)
        #expect(set.count == 4)
    }

    @Test("AppTab Sendable uyumlu olmali")
    func tabSendable() {
        let tab: any Sendable = AppTab.home
        #expect(tab is AppTab)
    }
}
