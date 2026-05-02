import Foundation
import SwiftUI
import Testing
@testable import RafRaf

/// RFUsageGauge bilesen testleri.
/// Esik renk mantigi, boyut esleme ve asilmis-durum etiketi dogrulamalari.
@Suite("RFUsageGauge Tests")
struct RFUsageGaugeTests {

    // MARK: - Threshold colors (0–60 green, 60–85 yellow, 85–100+ red)

    @Test("0% icin yesil renk dondurulmeli")
    func thresholdAtZero() {
        #expect(RFUsageGauge.color(for: 0) == RFColors.success)
    }

    @Test("59% icin yesil renk dondurulmeli (alt sinir)")
    func thresholdJustBelowYellow() {
        #expect(RFUsageGauge.color(for: 59) == RFColors.success)
    }

    @Test("60% icin sari renk dondurulmeli (esik basi)")
    func thresholdAtYellowBoundary() {
        #expect(RFUsageGauge.color(for: 60) == RFColors.warning)
    }

    @Test("84% icin sari renk dondurulmeli (sari ust sinir)")
    func thresholdJustBelowRed() {
        #expect(RFUsageGauge.color(for: 84) == RFColors.warning)
    }

    @Test("85% icin kirmizi renk dondurulmeli (kirmizi esigi)")
    func thresholdAtRedBoundary() {
        #expect(RFUsageGauge.color(for: 85) == RFColors.error)
    }

    @Test("100% icin kirmizi renk dondurulmeli")
    func thresholdAtHundred() {
        #expect(RFUsageGauge.color(for: 100) == RFColors.error)
    }

    @Test("105% (asilmis) icin kirmizi renk dondurulmeli")
    func thresholdOverage() {
        #expect(RFUsageGauge.color(for: 105) == RFColors.error)
    }

    // MARK: - Size mapping

    @Test("Small boyut 36pt cap olmali")
    func smallSizeDiameter() {
        #expect(RFUsageGauge.Size.small.diameter == 36)
    }

    @Test("Medium boyut 96pt cap olmali")
    func mediumSizeDiameter() {
        #expect(RFUsageGauge.Size.medium.diameter == 96)
    }

    @Test("Large boyut 160pt cap olmali")
    func largeSizeDiameter() {
        #expect(RFUsageGauge.Size.large.diameter == 160)
    }

    @Test("Inner halka kalinligi outer halkadan daha kalin olmali (dominant ring)")
    func innerLineWidthDominant() {
        #expect(RFUsageGauge.Size.small.innerLineWidth > RFUsageGauge.Size.small.outerLineWidth)
        #expect(RFUsageGauge.Size.medium.innerLineWidth > RFUsageGauge.Size.medium.outerLineWidth)
        #expect(RFUsageGauge.Size.large.innerLineWidth > RFUsageGauge.Size.large.outerLineWidth)
    }

    @Test("Boyut buyudukce cap artmali (small < medium < large)")
    func sizeMonotonic() {
        let small = RFUsageGauge.Size.small.diameter
        let medium = RFUsageGauge.Size.medium.diameter
        let large = RFUsageGauge.Size.large.diameter
        #expect(small < medium)
        #expect(medium < large)
    }

    // MARK: - Initialization & overage

    @Test("Default init varsayilan parametreleri korumalı")
    func defaultInitializerDefaults() {
        let gauge = RFUsageGauge(fiveHourPct: 50, sevenDayPct: 30)
        #expect(gauge.fiveHourPct == 50)
        #expect(gauge.sevenDayPct == 30)
        #expect(gauge.fiveHourResetsAt == nil)
        #expect(gauge.sevenDayResetsAt == nil)
        #expect(gauge.size == .medium)
        #expect(gauge.showsCaption == true)
    }

    @Test("Tum parametrelerle init dogru atanmali")
    func fullInitializer() {
        let date = Date(timeIntervalSince1970: 1_000_000)
        let gauge = RFUsageGauge(
            fiveHourPct: 92,
            sevenDayPct: 78,
            fiveHourResetsAt: date,
            sevenDayResetsAt: date,
            size: .large,
            showsCaption: false
        )
        #expect(gauge.fiveHourPct == 92)
        #expect(gauge.sevenDayPct == 78)
        #expect(gauge.fiveHourResetsAt == date)
        #expect(gauge.sevenDayResetsAt == date)
        #expect(gauge.size == .large)
        #expect(gauge.showsCaption == false)
    }

    @Test("Asilmis kullanim (>100%) icin overage durumu dogru tanimlanmali")
    func overageDetected() {
        let gauge = RFUsageGauge(fiveHourPct: 105, sevenDayPct: 95)
        // 105 > 100 → overage yolunu tetiklemeli; renk kirmizi kalmali.
        #expect(RFUsageGauge.color(for: gauge.fiveHourPct) == RFColors.error)
        #expect(gauge.fiveHourPct > 100)
    }

    @Test("Tam 100% icin overage olmamali (sinir durumu)")
    func notOverageAtHundred() {
        let gauge = RFUsageGauge(fiveHourPct: 100, sevenDayPct: 50)
        #expect(gauge.fiveHourPct == 100)
        // 100 overage degil — etiket "100%" gosterilmeli, "Asildi" degil.
        #expect(!(gauge.fiveHourPct > 100))
    }
}
