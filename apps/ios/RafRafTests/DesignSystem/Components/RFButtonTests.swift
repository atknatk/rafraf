import Foundation
import Testing
@testable import RafRaf

/// RFButton bilesen testleri.
@Suite("RFButton Tests")
struct RFButtonTests {

    @Test("RFButtonStyle tum varyantlari mevcut olmali")
    func buttonStyleVariants() {
        let styles: [RFButtonStyle] = [
            .primary, .secondary, .outline, .ghost, .destructive
        ]
        #expect(styles.count == 5)
    }

    @Test("RFButtonSize small vertical padding dogru olmali")
    func buttonSizeSmallVerticalPadding() {
        let size = RFButtonSize.small
        #expect(size.verticalPadding == RFSpacing.xs)
    }

    @Test("RFButtonSize medium vertical padding dogru olmali")
    func buttonSizeMediumVerticalPadding() {
        let size = RFButtonSize.medium
        #expect(size.verticalPadding == RFSpacing.sm)
    }

    @Test("RFButtonSize large vertical padding dogru olmali")
    func buttonSizeLargeVerticalPadding() {
        let size = RFButtonSize.large
        #expect(size.verticalPadding == RFSpacing.md)
    }

    @Test("RFButtonSize small horizontal padding dogru olmali")
    func buttonSizeSmallHorizontalPadding() {
        let size = RFButtonSize.small
        #expect(size.horizontalPadding == RFSpacing.sm)
    }

    @Test("RFButtonSize medium horizontal padding dogru olmali")
    func buttonSizeMediumHorizontalPadding() {
        let size = RFButtonSize.medium
        #expect(size.horizontalPadding == RFSpacing.md)
    }

    @Test("RFButtonSize large horizontal padding dogru olmali")
    func buttonSizeLargeHorizontalPadding() {
        let size = RFButtonSize.large
        #expect(size.horizontalPadding == RFSpacing.xl)
    }
}
