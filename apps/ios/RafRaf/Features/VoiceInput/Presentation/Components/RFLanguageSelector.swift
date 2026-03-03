import SwiftUI

/// Dil secim bileseni.
/// Turkce ve Ingilizce arasinda gecis yapar.
struct RFLanguageSelector: View {
    @Binding var selectedLanguage: VoiceLanguage
    let onLanguageChanged: (VoiceLanguage) -> Void

    var body: some View {
        HStack(spacing: RFSpacing.xxs) {
            ForEach(VoiceLanguage.allCases, id: \.rawValue) { language in
                RFButton(
                    language.displayName,
                    style: language == selectedLanguage ? .primary : .ghost,
                    size: .small
                ) {
                    if language != selectedLanguage {
                        selectedLanguage = language
                        onLanguageChanged(language)
                    }
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(String(localized: "voiceInput.languageSelector.label"))
    }
}

#Preview {
    @Previewable @State var language: VoiceLanguage = .turkish

    RFLanguageSelector(
        selectedLanguage: $language,
        onLanguageChanged: { _ in }
    )
    .padding()
}
