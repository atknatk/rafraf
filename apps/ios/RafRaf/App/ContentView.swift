import SwiftUI

/// Ana tab navigation yapisi.
/// Uygulamanin kok gorunumu, tab bar ile feature ekranlarini barindirir.
struct ContentView: View {
    @State private var selectedTab: AppTab = .home

    var body: some View {
        TabView(selection: $selectedTab) {
            HomeView()
                .tabItem {
                    Label(String(localized: "tab.home"), systemImage: "house.fill")
                }
                .tag(AppTab.home)

            ChatView()
                .tabItem {
                    Label(String(localized: "tab.chat"), systemImage: "message.fill")
                }
                .tag(AppTab.chat)

            SettingsView()
                .tabItem {
                    Label(String(localized: "tab.settings"), systemImage: "gearshape.fill")
                }
                .tag(AppTab.settings)
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
