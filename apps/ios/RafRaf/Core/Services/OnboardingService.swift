import Foundation

/// Ilk kullanim onboarding tamamlanma durumunu takip eder.
@MainActor final class OnboardingService {
    static let shared = OnboardingService()
    private let key = "rafraf.onboarding.completed"

    private init() {}

    var hasCompletedOnboarding: Bool {
        get { UserDefaults.standard.bool(forKey: key) }
        set { UserDefaults.standard.set(newValue, forKey: key) }
    }

    func completeOnboarding() {
        hasCompletedOnboarding = true
    }

    func resetOnboarding() {
        hasCompletedOnboarding = false
    }
}
