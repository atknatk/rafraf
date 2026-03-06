import AppIntents
import Foundation
import UIKit

/// Proje durumunu Siri üzerinden öğrenmek için AppIntent.
@available(iOS 16.0, *)
struct CheckProjectStatusIntent: AppIntent {
    static let title: LocalizedStringResource = "intent.projectStatus.title"
    static let description = IntentDescription(
        LocalizedStringResource("intent.projectStatus.description")
    )
    static let openAppWhenRun: Bool = true

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        if let url = URL(string: "rafraf://projects") {
            _ = await UIApplication.shared.open(url)
        }
        return .result(
            dialog: IntentDialog(stringLiteral: String(localized: "intent.projectStatus.result"))
        )
    }
}
