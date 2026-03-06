import AppIntents
import Foundation
import UIKit

/// Siri üzerinden RafRaf'a soru sormak için AppIntent.
/// "Hey Siri, RafRaf'a 'deploy durumu nedir' sor" şeklinde kullanılır.
@available(iOS 16.0, *)
struct AskRafRafIntent: AppIntent {
    static let title: LocalizedStringResource = "intent.ask.title"
    static let description = IntentDescription(
        LocalizedStringResource("intent.ask.description")
    )
    static let openAppWhenRun: Bool = true

    @Parameter(title: LocalizedStringResource("intent.ask.parameter.question"))
    var question: String

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let encoded = question.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? question
        let urlString = "rafraf://chat?message=\(encoded)"
        if let url = URL(string: urlString) {
            _ = await UIApplication.shared.open(url)
        }
        let dialogText = String(localized: "intent.ask.result") + " '\(question)'"
        return .result(dialog: IntentDialog(stringLiteral: dialogText))
    }
}
