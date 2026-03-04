import SwiftUI

/// SwiftUI View uzantilari.
extension View {

    /// Kosullu modifier uygular.
    @ViewBuilder
    func `if`<Content: View>(
        _ condition: Bool,
        transform: (Self) -> Content
    ) -> some View {
        if condition {
            transform(self)
        } else {
            self
        }
    }

    /// Opsiyonel deger varsa modifier uygular.
    @ViewBuilder
    func ifLet<Value, Content: View>(
        _ value: Value?,
        transform: (Self, Value) -> Content
    ) -> some View {
        if let value {
            transform(self, value)
        } else {
            self
        }
    }

    /// RFShadow spec ile golge uygular.
    func rfShadow(_ spec: RFShadow.ShadowSpec) -> some View {
        self.shadow(color: spec.color, radius: spec.radius, x: spec.x, y: spec.y)
    }

    /// Staggered giris animasyonu — opacity + offset ile.
    func rfEntrance(isAppeared: Bool, delay: Double) -> some View {
        self
            .opacity(isAppeared ? 1 : 0)
            .offset(y: isAppeared ? 0 : 16)
            .animation(RFAnimation.springResponsive.delay(delay), value: isAppeared)
    }

    /// Katmanli golge ile derinlik efekti uygular (iki gecisli).
    @ViewBuilder
    func rfElevation(_ level: RFElevationLevel) -> some View {
        switch level {
        case .low:
            self
                .shadow(color: .black.opacity(0.04), radius: 1, y: 1)
                .shadow(color: .black.opacity(0.06), radius: 4, y: 2)
        case .medium:
            self
                .shadow(color: .black.opacity(0.06), radius: 2, y: 1)
                .shadow(color: .black.opacity(0.10), radius: 12, y: 6)
        case .high:
            self
                .shadow(color: .black.opacity(0.08), radius: 4, y: 2)
                .shadow(color: .black.opacity(0.14), radius: 20, y: 10)
        }
    }
}
