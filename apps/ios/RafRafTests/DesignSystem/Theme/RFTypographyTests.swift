import Foundation
import SwiftUI
import Testing
@testable import RafRaf

/// RFTypography tema testleri.
@Suite("RFTypography Tests")
struct RFTypographyTests {

    @Test("RFTypography largeTitle mevcut olmali")
    func largeTitleExists() {
        let font = RFTypography.largeTitle
        #expect(font == Font.largeTitle.weight(.bold))
    }

    @Test("RFTypography title mevcut olmali")
    func titleExists() {
        let font = RFTypography.title
        #expect(font == Font.title2.weight(.semibold))
    }

    @Test("RFTypography subtitle mevcut olmali")
    func subtitleExists() {
        let font = RFTypography.subtitle
        #expect(font == Font.title3.weight(.medium))
    }

    @Test("RFTypography body mevcut olmali")
    func bodyExists() {
        let font = RFTypography.body
        #expect(font == Font.body)
    }

    @Test("RFTypography bodyBold mevcut olmali")
    func bodyBoldExists() {
        let font = RFTypography.bodyBold
        #expect(font == Font.body.weight(.semibold))
    }

    @Test("RFTypography caption mevcut olmali")
    func captionExists() {
        let font = RFTypography.caption
        #expect(font == Font.caption)
    }

    @Test("RFTypography captionBold mevcut olmali")
    func captionBoldExists() {
        let font = RFTypography.captionBold
        #expect(font == Font.caption.weight(.semibold))
    }

    @Test("RFTypography button mevcut olmali")
    func buttonExists() {
        let font = RFTypography.button
        #expect(font == Font.body.weight(.semibold))
    }

    @Test("RFTypography tabBar mevcut olmali")
    func tabBarExists() {
        let font = RFTypography.tabBar
        #expect(font == Font.caption2)
    }
}
