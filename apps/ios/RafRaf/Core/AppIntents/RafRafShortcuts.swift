import AppIntents
import Foundation

/// RafRaf için Siri kısayolları sağlayıcısı.
/// "Hey Siri, RafRaf'a sor" gibi komutları etkinleştirir.
@available(iOS 16.0, *)
struct RafRafShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: AskRafRafIntent(),
            phrases: [
                "RafRaf'a \(.applicationName) ile sor",
                "\(.applicationName) ile proje durumunu öğren",
            ],
            shortTitle: LocalizedStringResource("shortcut.ask.title"),
            systemImageName: "brain.head.profile"
        )
        AppShortcut(
            intent: CheckProjectStatusIntent(),
            phrases: [
                "\(.applicationName) ile proje durumunu kontrol et",
                "\(.applicationName)'a proje özeti",
            ],
            shortTitle: LocalizedStringResource("shortcut.projectStatus.title"),
            systemImageName: "chart.bar"
        )
    }
}
