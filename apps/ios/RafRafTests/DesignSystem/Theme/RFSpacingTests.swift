import Foundation
import Testing
@testable import RafRaf

/// RFSpacing tema testleri.
@Suite("RFSpacing Tests")
struct RFSpacingTests {

    @Test("RFSpacing xxs 4pt olmali")
    func spacingXxs() {
        #expect(RFSpacing.xxs == 4)
    }

    @Test("RFSpacing xs 8pt olmali")
    func spacingXs() {
        #expect(RFSpacing.xs == 8)
    }

    @Test("RFSpacing sm 12pt olmali")
    func spacingSm() {
        #expect(RFSpacing.sm == 12)
    }

    @Test("RFSpacing md 16pt olmali")
    func spacingMd() {
        #expect(RFSpacing.md == 16)
    }

    @Test("RFSpacing lg 20pt olmali")
    func spacingLg() {
        #expect(RFSpacing.lg == 20)
    }

    @Test("RFSpacing xl 24pt olmali")
    func spacingXl() {
        #expect(RFSpacing.xl == 24)
    }

    @Test("RFSpacing xxl 32pt olmali")
    func spacingXxl() {
        #expect(RFSpacing.xxl == 32)
    }

    @Test("RFSpacing xxxl 48pt olmali")
    func spacingXxxl() {
        #expect(RFSpacing.xxxl == 48)
    }

    @Test("RFSpacing degerleri artan sirada olmali")
    func spacingValuesAscending() {
        #expect(RFSpacing.xxs < RFSpacing.xs)
        #expect(RFSpacing.xs < RFSpacing.sm)
        #expect(RFSpacing.sm < RFSpacing.md)
        #expect(RFSpacing.md < RFSpacing.lg)
        #expect(RFSpacing.lg < RFSpacing.xl)
        #expect(RFSpacing.xl < RFSpacing.xxl)
        #expect(RFSpacing.xxl < RFSpacing.xxxl)
    }
}
