import SwiftUI

/// Gercek zamanli transkripsiyon gosterim overlay'i.
/// Kayit sirasinda interim ve final transkripsiyon metinlerini gosterir.
struct RFTranscriptionOverlay: View {
    let finalText: String
    let interimText: String
    let isProcessing: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xs) {
            if !combinedText.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                        if !finalText.isEmpty {
                            RFText(finalText, style: .body)
                                .foregroundStyle(RFColors.fallbackTextPrimary)
                        }

                        if !interimText.isEmpty {
                            RFText(interimText, style: .body)
                                .foregroundStyle(RFColors.fallbackTextSecondary)
                                .italic()
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 120)
            } else if isProcessing {
                HStack(spacing: RFSpacing.xs) {
                    ProgressView()
                        .controlSize(.small)
                    RFText(
                        String(localized: "voiceInput.processing"),
                        style: .caption
                    )
                    .foregroundStyle(RFColors.fallbackTextSecondary)
                }
            } else {
                RFText(
                    String(localized: "voiceInput.listening"),
                    style: .caption
                )
                .foregroundStyle(RFColors.fallbackTextSecondary)
            }
        }
        .padding(RFSpacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RFColors.fallbackSurface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Private

    private var combinedText: String {
        [finalText, interimText]
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFTranscriptionOverlay(
            finalText: "",
            interimText: "",
            isProcessing: false
        )

        RFTranscriptionOverlay(
            finalText: "Merhaba, bugun",
            interimText: "hava nasil",
            isProcessing: false
        )

        RFTranscriptionOverlay(
            finalText: "",
            interimText: "",
            isProcessing: true
        )
    }
    .padding()
}
