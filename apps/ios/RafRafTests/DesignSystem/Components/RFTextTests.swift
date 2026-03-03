import Foundation
import Testing
@testable import RafRaf

/// RFText bilesen testleri.
@Suite("RFText Tests")
struct RFTextTests {

    @Test("RFTextStyle tum varyantlari mevcut olmali")
    func textStyleVariants() {
        let styles: [RFTextStyle] = [
            .largeTitle, .title, .subtitle,
            .body, .bodyBold,
            .caption, .captionBold
        ]
        #expect(styles.count == 7)
    }

    @Test("RFTextStyle largeTitle font RFTypography.largeTitle olmali")
    func largeTitleFont() {
        let style = RFTextStyle.largeTitle
        #expect(style.font == RFTypography.largeTitle)
    }

    @Test("RFTextStyle title font RFTypography.title olmali")
    func titleFont() {
        let style = RFTextStyle.title
        #expect(style.font == RFTypography.title)
    }

    @Test("RFTextStyle body font RFTypography.body olmali")
    func bodyFont() {
        let style = RFTextStyle.body
        #expect(style.font == RFTypography.body)
    }

    @Test("RFTextStyle caption font RFTypography.caption olmali")
    func captionFont() {
        let style = RFTextStyle.caption
        #expect(style.font == RFTypography.caption)
    }
}
