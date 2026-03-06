import SwiftUI

/// RafRaf - AI Project Supervisor
/// Ana uygulama giris noktasi.
@main
struct RafRafApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @State private var showOnboarding = !OnboardingService.shared.hasCompletedOnboarding

    var body: some Scene {
        WindowGroup {
            ContentView()
                .fullScreenCover(isPresented: $showOnboarding) {
                    OnboardingView {
                        showOnboarding = false
                    }
                }
        }
    }
}
