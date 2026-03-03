import SwiftUI

/// TTS ses secimi bileseni.
/// Kullanilabilir sesleri listeler ve secim yapilmasini saglar.
struct RFVoiceSelector: View {
    @Binding var selectedVoice: TTSVoice

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xs) {
            RFText(
                String(localized: "voiceOutput.voiceSelector.title"),
                style: .caption
            )
            .foregroundStyle(RFColors.fallbackTextSecondary)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: RFSpacing.xs) {
                    ForEach(TTSVoice.allCases, id: \.self) { voice in
                        voiceChip(voice)
                    }
                }
                .padding(.horizontal, RFSpacing.xxs)
            }
        }
    }

    @ViewBuilder
    private func voiceChip(_ voice: TTSVoice) -> some View {
        let isSelected = voice == selectedVoice

        Button {
            selectedVoice = voice
        } label: {
            RFText(
                voice.displayName,
                style: .caption
            )
            .padding(.horizontal, RFSpacing.sm)
            .padding(.vertical, RFSpacing.xs)
            .background(isSelected ? RFColors.fallbackPrimary : RFColors.fallbackSurface)
            .foregroundStyle(isSelected ? .white : RFColors.fallbackTextPrimary)
            .clipShape(Capsule())
        }
        .accessibilityLabel(Text(voice.displayName))
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}

#Preview {
    struct PreviewWrapper: View {
        @State private var voice: TTSVoice = .alloy

        var body: some View {
            RFVoiceSelector(selectedVoice: $voice)
                .padding()
        }
    }

    return PreviewWrapper()
}
