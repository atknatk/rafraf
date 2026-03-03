import SwiftUI

/// Onay secenegi butonu.
/// Approval card icerisindeki her bir secenek icin stil-bazli buton.
struct RFApprovalOptionButton: View {
    /// Secenek modeli.
    let option: ApprovalOption
    /// Buton devre disi mi.
    let isDisabled: Bool
    /// Yuklenme durumunda mi.
    let isLoading: Bool
    /// Tiklandiginda cagrilacak aksiyon.
    let action: () -> Void

    var body: some View {
        RFButton(
            option.label,
            style: buttonStyle,
            size: .medium,
            isLoading: isLoading,
            isDisabled: isDisabled,
            action: action
        )
        .accessibilityLabel(option.label)
        .accessibilityHint(
            String(localized: "approval.option.hint \(option.label)")
        )
    }

    // MARK: - Private

    /// ApprovalOptionStyle -> RFButtonStyle eslesmesi.
    private var buttonStyle: RFButtonStyle {
        switch option.style {
        case .primary:
            return .primary
        case .danger:
            return .destructive
        case .secondary:
            return .secondary
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.sm) {
        RFApprovalOptionButton(
            option: ApprovalOption(
                id: "approve",
                label: String(localized: "approval.action.approve"),
                style: .primary
            ),
            isDisabled: false,
            isLoading: false
        ) {}

        RFApprovalOptionButton(
            option: ApprovalOption(
                id: "reject",
                label: String(localized: "approval.action.reject"),
                style: .danger
            ),
            isDisabled: false,
            isLoading: false
        ) {}

        RFApprovalOptionButton(
            option: ApprovalOption(
                id: "detail",
                label: String(localized: "approval.action.detail"),
                style: .secondary
            ),
            isDisabled: false,
            isLoading: false
        ) {}

        RFApprovalOptionButton(
            option: ApprovalOption(
                id: "approve",
                label: String(localized: "approval.action.approve"),
                style: .primary
            ),
            isDisabled: false,
            isLoading: true
        ) {}
    }
    .padding()
}
