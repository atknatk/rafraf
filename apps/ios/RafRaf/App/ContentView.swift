import SwiftUI

/// Ana tab navigation yapisi.
/// Uygulamanin kok gorunumu, tab bar ile feature ekranlarini barindirir.
struct ContentView: View {
    @State private var selectedTab: AppTab = .home

    var body: some View {
        TabView(selection: $selectedTab) {
            Tab(String(localized: "tab.home"), systemImage: "house.fill", value: .home) {
                HomeView()
            }

            Tab(String(localized: "tab.chat"), systemImage: "message.fill", value: .chat) {
                ChatView()
            }

            Tab(String(localized: "tab.settings"), systemImage: "gearshape.fill", value: .settings) {
                SettingsView()
            }
        }
    }
}

/// Uygulama tab tipleri.
enum AppTab: String, Hashable, Sendable {
    case home
    case chat
    case settings
}

#Preview {
    ContentView()
}
