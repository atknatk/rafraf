import SwiftUI

/// RafRaf ayarlar satiri bileseni.
/// Toggle, picker veya bilgi gosterimi icin kullanilir.
struct RFSettingsRow: View {
    let icon: String
    let iconColor: Color
    let title: String
    let subtitle: String?

    init(
        icon: String,
        iconColor: Color = RFColors.fallbackPrimary,
        title: String,
        subtitle: String? = nil
    ) {
        self.icon = icon
        self.iconColor = iconColor
        self.title = title
        self.subtitle = subtitle
    }

    var body: some View {
        HStack(spacing: RFSpacing.sm) {
            Image(systemName: icon)
                .font(.body)
                .foregroundStyle(.white)
                .frame(width: 30, height: 30)
                .background(
                    LinearGradient(
                        colors: [iconColor, iconColor.opacity(0.7)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .clipShape(RoundedRectangle(cornerRadius: 7))

            VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                RFText(title, style: .body)

                if let subtitle {
                    RFText(subtitle, style: .caption)
                }
            }
        }
    }
}

/// Toggle iceren ayarlar satiri.
struct RFSettingsToggleRow: View {
    let icon: String
    let iconColor: Color
    let title: String
    @Binding var isOn: Bool
    let onChanged: (Bool) -> Void

    init(
        icon: String,
        iconColor: Color = RFColors.fallbackPrimary,
        title: String,
        isOn: Binding<Bool>,
        onChanged: @escaping (Bool) -> Void = { _ in }
    ) {
        self.icon = icon
        self.iconColor = iconColor
        self.title = title
        self._isOn = isOn
        self.onChanged = onChanged
    }

    var body: some View {
        Toggle(isOn: $isOn) {
            RFSettingsRow(
                icon: icon,
                iconColor: iconColor,
                title: title
            )
        }
        .tint(RFColors.fallbackPrimary)
        .onChange(of: isOn) { _, newValue in
            onChanged(newValue)
        }
    }
}

#Preview {
    List {
        RFSettingsRow(
            icon: "speaker.wave.2",
            title: "Ses Ayarlari"
        )
        RFSettingsRow(
            icon: "bell",
            iconColor: .red,
            title: "Bildirimler",
            subtitle: "Push bildirimleri yonet"
        )
        RFSettingsToggleRow(
            icon: "moon",
            iconColor: .purple,
            title: "Dark Mode",
            isOn: .constant(true)
        )
    }
}
