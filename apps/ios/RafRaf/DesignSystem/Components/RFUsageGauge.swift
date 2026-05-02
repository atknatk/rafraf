import SwiftUI

/// RafRaf kullanim gostergesi — Claude Code Max plan kotalari icin ic ice iki halka.
/// Ic halka: 5 saatlik rolling kota (dominant), Dis halka: 7 gunluk haftalik kota.
/// Esik renkleri: 0–60% yesil, 60–85% sari, 85–100% kirmizi, 100%+ asilmis (subtle pulse).
/// T1.9 — saf bilesen; DTO/ViewModel baglantisi T1.6'da yapilir.
struct RFUsageGauge: View {

    // MARK: - Public types

    /// Gauge boyut varyantlari.
    enum Size: Sendable {
        /// Statusbar/kompakt kullanim.
        case small
        /// Varsayilan boyut.
        case medium
        /// Ayarlar ekrani / odakli gorunum.
        case large

        /// Toplam dis cap (pt).
        var diameter: CGFloat {
            switch self {
            case .small: return 36
            case .medium: return 96
            case .large: return 160
            }
        }

        /// Ic (5h) halka kalinligi.
        var innerLineWidth: CGFloat {
            switch self {
            case .small: return 4
            case .medium: return 8
            case .large: return 12
            }
        }

        /// Dis (7d) halka kalinligi.
        var outerLineWidth: CGFloat {
            switch self {
            case .small: return 2
            case .medium: return 4
            case .large: return 6
            }
        }

        /// Halkalar arasi bosluk.
        var ringSpacing: CGFloat {
            switch self {
            case .small: return 2
            case .medium: return 4
            case .large: return 6
            }
        }

        /// Merkez yuzde fontu.
        var centerFont: Font {
            switch self {
            case .small: return .system(size: 10, weight: .bold, design: .rounded)
            case .medium: return .system(size: 22, weight: .bold, design: .rounded)
            case .large: return .system(size: 36, weight: .bold, design: .rounded)
            }
        }

        /// Merkez "5h" etiketi fontu.
        var centerSubFont: Font {
            switch self {
            case .small: return .system(size: 7, weight: .semibold, design: .rounded)
            case .medium: return .system(size: 11, weight: .semibold, design: .rounded)
            case .large: return .system(size: 14, weight: .semibold, design: .rounded)
            }
        }

        /// Caption (resets-in) fontu.
        var captionFont: Font {
            switch self {
            case .small: return .system(size: 9, weight: .medium)
            case .medium: return .system(size: 12, weight: .medium)
            case .large: return .system(size: 14, weight: .medium)
            }
        }

        /// Caption ile gauge arasi bosluk.
        var captionSpacing: CGFloat {
            switch self {
            case .small: return RFSpacing.xxs
            case .medium: return RFSpacing.xs
            case .large: return RFSpacing.sm
            }
        }
    }

    // MARK: - Properties

    let fiveHourPct: Int
    let sevenDayPct: Int
    let fiveHourResetsAt: Date?
    let sevenDayResetsAt: Date?
    let size: Size
    let showsCaption: Bool

    @State private var pulse: Bool = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    // MARK: - Init

    init(
        fiveHourPct: Int,
        sevenDayPct: Int,
        fiveHourResetsAt: Date? = nil,
        sevenDayResetsAt: Date? = nil,
        size: Size = .medium,
        showsCaption: Bool = true
    ) {
        self.fiveHourPct = fiveHourPct
        self.sevenDayPct = sevenDayPct
        self.fiveHourResetsAt = fiveHourResetsAt
        self.sevenDayResetsAt = sevenDayResetsAt
        self.size = size
        self.showsCaption = showsCaption
    }

    // MARK: - Body

    var body: some View {
        VStack(spacing: size.captionSpacing) {
            gauge
            if showsCaption, size != .small {
                caption
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text(accessibilityLabel))
        .accessibilityValue(Text(accessibilityValue))
        .accessibilityHint(Text(String(localized: "usage.gauge.accessibility.hint")))
    }

    // MARK: - Gauge (rings + center)

    private var gauge: some View {
        ZStack {
            // Outer ring (7-day) track + progress
            Circle()
                .stroke(
                    Self.color(for: sevenDayPct).opacity(0.15),
                    lineWidth: size.outerLineWidth
                )
                .frame(width: outerDiameter, height: outerDiameter)

            Circle()
                .trim(from: 0, to: clampedRatio(sevenDayPct))
                .stroke(
                    Self.color(for: sevenDayPct),
                    style: StrokeStyle(lineWidth: size.outerLineWidth, lineCap: .round)
                )
                .frame(width: outerDiameter, height: outerDiameter)
                .rotationEffect(.degrees(-90))
                .animation(.easeOut(duration: 0.6), value: sevenDayPct)

            // Inner ring (5-hour) track + progress
            Circle()
                .stroke(
                    Self.color(for: fiveHourPct).opacity(0.15),
                    lineWidth: size.innerLineWidth
                )
                .frame(width: innerDiameter, height: innerDiameter)

            Circle()
                .trim(from: 0, to: clampedRatio(fiveHourPct))
                .stroke(
                    Self.color(for: fiveHourPct),
                    style: StrokeStyle(lineWidth: size.innerLineWidth, lineCap: .round)
                )
                .frame(width: innerDiameter, height: innerDiameter)
                .rotationEffect(.degrees(-90))
                .scaleEffect(isOverage && !reduceMotion ? (pulse ? 1.02 : 1.0) : 1.0)
                .opacity(isOverage && !reduceMotion ? (pulse ? 0.85 : 1.0) : 1.0)
                .animation(.easeOut(duration: 0.6), value: fiveHourPct)
                .animation(
                    isOverage && !reduceMotion
                        ? .easeInOut(duration: 1.1).repeatForever(autoreverses: true)
                        : .default,
                    value: pulse
                )

            // Center label
            centerLabel
        }
        .frame(width: outerDiameter, height: outerDiameter)
        .onAppear {
            if isOverage, !reduceMotion {
                pulse = true
            }
        }
        .onChange(of: isOverage) { _, newValue in
            pulse = newValue && !reduceMotion
        }
    }

    @ViewBuilder
    private var centerLabel: some View {
        VStack(spacing: 0) {
            if isOverage {
                Text(String(localized: "usage.over"))
                    .font(size.centerSubFont)
                    .foregroundStyle(Self.color(for: fiveHourPct))
                Text("\(displayPct)%")
                    .font(size.centerFont)
                    .foregroundStyle(Self.color(for: fiveHourPct))
                    .monospacedDigit()
            } else {
                Text("\(displayPct)%")
                    .font(size.centerFont)
                    .foregroundStyle(Self.color(for: fiveHourPct))
                    .monospacedDigit()
                if size != .small {
                    Text(String(localized: "usage.fiveHour.short"))
                        .font(size.centerSubFont)
                        .foregroundStyle(RFColors.fallbackTextSecondary)
                }
            }
        }
    }

    // MARK: - Caption

    @ViewBuilder
    private var caption: some View {
        if let resetsAt = fiveHourResetsAt, resetsAt > .now {
            Text(captionText(for: resetsAt))
                .font(size.captionFont)
                .foregroundStyle(RFColors.fallbackTextSecondary)
                .multilineTextAlignment(.center)
        }
    }

    private func captionText(for date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        let relative = formatter.localizedString(for: date, relativeTo: .now)
        return String(format: String(localized: "usage.fiveHour.resetsIn"), relative)
    }

    // MARK: - Geometry helpers

    private var outerDiameter: CGFloat {
        size.diameter
    }

    private var innerDiameter: CGFloat {
        // Pull inner ring inside the outer ring stroke + spacing.
        let inset = size.outerLineWidth + size.ringSpacing + size.innerLineWidth
        return max(size.diameter - inset * 2, 0)
    }

    // MARK: - Computed state

    /// 0...100 araliginda gosterilen yuzde (asma durumunda 100'e kirpilir).
    private var displayPct: Int {
        max(0, min(fiveHourPct, 100))
    }

    /// Halka ilerleme orani (0...1).
    private func clampedRatio(_ pct: Int) -> CGFloat {
        let bounded = max(0, min(pct, 100))
        return CGFloat(bounded) / 100.0
    }

    private var isOverage: Bool {
        fiveHourPct > 100
    }

    // MARK: - Threshold color (testable)

    /// Yuzde degerine gore esik rengi.
    /// 0–60% yesil, 60–85% sari, 85–100% kirmizi, 100%+ kirmizi (asilmis).
    static func color(for pct: Int) -> Color {
        switch pct {
        case ..<60:
            return RFColors.success
        case ..<85:
            return RFColors.warning
        default:
            return RFColors.error
        }
    }

    // MARK: - Accessibility

    private var accessibilityLabel: String {
        String(
            format: String(localized: "usage.gauge.accessibility.label"),
            String(fiveHourPct),
            String(sevenDayPct)
        )
    }

    private var accessibilityValue: String {
        if isOverage {
            return String(localized: "usage.over")
        }
        return "\(displayPct)%"
    }
}

#Preview("Variants") {
    VStack(spacing: 32) {
        RFUsageGauge(
            fiveHourPct: 12,
            sevenDayPct: 8,
            fiveHourResetsAt: .now.addingTimeInterval(3600 * 4),
            sevenDayResetsAt: .now.addingTimeInterval(3600 * 24 * 5)
        )
        RFUsageGauge(
            fiveHourPct: 72,
            sevenDayPct: 45,
            fiveHourResetsAt: .now.addingTimeInterval(60 * 30),
            sevenDayResetsAt: nil
        )
        RFUsageGauge(
            fiveHourPct: 92,
            sevenDayPct: 78,
            fiveHourResetsAt: .now.addingTimeInterval(60 * 8),
            sevenDayResetsAt: .now.addingTimeInterval(3600 * 12)
        )
        RFUsageGauge(
            fiveHourPct: 105,
            sevenDayPct: 95,
            size: .small,
            showsCaption: false
        )
    }
    .padding()
    .background(RFColors.fallbackBackground)
}

#Preview("Sizes") {
    HStack(alignment: .center, spacing: 24) {
        RFUsageGauge(fiveHourPct: 65, sevenDayPct: 40, size: .small, showsCaption: false)
        RFUsageGauge(
            fiveHourPct: 65,
            sevenDayPct: 40,
            fiveHourResetsAt: .now.addingTimeInterval(3600 * 2),
            size: .medium
        )
        RFUsageGauge(
            fiveHourPct: 65,
            sevenDayPct: 40,
            fiveHourResetsAt: .now.addingTimeInterval(3600 * 2),
            size: .large
        )
    }
    .padding()
    .background(RFColors.fallbackBackground)
}
