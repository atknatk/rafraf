import SwiftUI

/// Merkezi gecis animasyonlari.
/// Inline tanimli gecisler yerine bu enum kullanilir.
@MainActor
enum RFTransition {

    /// Kart/icerik gorunumu — scale up + fade.
    static let cardAppear = AnyTransition
        .scale(scale: 0.92)
        .combined(with: .opacity)

    /// Alttan kayma — modal/sheet benzeri.
    static let slideUp = AnyTransition
        .move(edge: .bottom)
        .combined(with: .opacity)

    /// Sagdan kayma — navigation push hissi.
    static let slideForward = AnyTransition
        .move(edge: .trailing)
        .combined(with: .opacity)

    /// Soldan kayma — navigation pop hissi.
    static let slideBack = AnyTransition
        .move(edge: .leading)
        .combined(with: .opacity)

    /// Asimetrik chat mesaji — scale ile girer, fade ile cikar.
    static let chatMessage = AnyTransition.asymmetric(
        insertion: .scale(scale: 0.95).combined(with: .opacity),
        removal: .opacity
    )

    /// Basit fade — overlay/banner icin.
    static let fade = AnyTransition.opacity
}
