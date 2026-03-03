import SwiftUI

/// Ses hizi kontrol bileseni.
/// Slider ile oynatma hizini ayarlar.
struct RFSpeedControl: View {
    @Binding var speed: Double

    /// Hiz preset degerleri.
    private static let presets: [Double] = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xs) {
            HStack {
                RFText(
                    String(localized: "voiceOutput.speedControl.title"),
                    style: .caption
                )
                .foregroundStyle(RFColors.fallbackTextSecondary)

                Spacer()

                RFText(
                    String(format: "%.2fx", speed),
                    style: .caption
                )
                .foregroundStyle(RFColors.fallbackPrimary)
            }

            // Preset butonlari
            HStack(spacing: RFSpacing.xs) {
                ForEach(Self.presets, id: \.self) { preset in
                    presetButton(preset)
                }
            }
        }
    }

    @ViewBuilder
    private func presetButton(_ preset: Double) -> some View {
        let isSelected = abs(speed - preset) < 0.01

        Button {
            speed = preset
        } label: {
            RFText(
                formatSpeed(preset),
                style: .caption
            )
            .padding(.horizontal, RFSpacing.xs)
            .padding(.vertical, RFSpacing.xxs)
            .background(isSelected ? RFColors.fallbackPrimary : RFColors.fallbackSurface)
            .foregroundStyle(isSelected ? .white : RFColors.fallbackTextPrimary)
            .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .accessibilityLabel(Text(String(localized: "voiceOutput.speedControl.preset \(formatSpeed(preset))")))
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }

    private func formatSpeed(_ value: Double) -> String {
        if value == floor(value) {
            return String(format: "%.0fx", value)
        }
        return String(format: "%.2fx", value)
    }
}

#Preview {
    struct PreviewWrapper: View {
        @State private var speed: Double = 1.0

        var body: some View {
            RFSpeedControl(speed: $speed)
                .padding()
        }
    }

    return PreviewWrapper()
}
