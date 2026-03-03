import SwiftUI

/// Biyometrik dogrulama butonu.
/// Face ID veya Touch ID ikonunu gosterir.
struct RFBiometricButton: View {
    let biometricType: BiometricType
    let isLoading: Bool
    let action: () -> Void

    init(
        biometricType: BiometricType,
        isLoading: Bool = false,
        action: @escaping () -> Void
    ) {
        self.biometricType = biometricType
        self.isLoading = isLoading
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: RFSpacing.xs) {
                if isLoading {
                    ProgressView()
                        .tint(RFColors.fallbackPrimary)
                } else {
                    Image(systemName: biometricIconName)
                        .font(.title2)
                        .foregroundStyle(RFColors.fallbackPrimary)
                }

                RFText(biometricTitle, style: .body, color: RFColors.fallbackPrimary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, RFSpacing.sm)
            .background(RFColors.fallbackSurface)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay {
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(RFColors.fallbackPrimary, lineWidth: 1)
            }
        }
        .disabled(isLoading)
    }

    private var biometricIconName: String {
        switch biometricType {
        case .faceID:
            return "faceid"
        case .touchID:
            return "touchid"
        case .opticID:
            return "opticid"
        case .none:
            return "lock.fill"
        }
    }

    private var biometricTitle: String {
        switch biometricType {
        case .faceID:
            return String(localized: "auth.biometric.faceID")
        case .touchID:
            return String(localized: "auth.biometric.touchID")
        case .opticID:
            return String(localized: "auth.biometric.opticID")
        case .none:
            return String(localized: "auth.biometric.unavailable")
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFBiometricButton(biometricType: .faceID) {}
        RFBiometricButton(biometricType: .touchID) {}
        RFBiometricButton(biometricType: .faceID, isLoading: true) {}
    }
    .padding()
}
