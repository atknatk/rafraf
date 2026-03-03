import Foundation
import Testing
@testable import RafRaf

/// RFCard bilesen testleri.
@Suite("RFCard Tests")
struct RFCardTests {

    @Test("RFCardStyle standard ve interactive varyantlari mevcut olmali")
    func cardStyleVariants() {
        let standard = RFCardStyle.standard
        let interactive = RFCardStyle.interactive

        #expect(standard != interactive)
    }

    @Test("RFCardStyle standard enum degeri dogru olmali")
    func cardStyleStandardExists() {
        let style: RFCardStyle = .standard
        switch style {
        case .standard:
            #expect(true)
        case .interactive:
            #expect(Bool(false), "Standard yerine interactive geldi")
        }
    }

    @Test("RFCardStyle interactive enum degeri dogru olmali")
    func cardStyleInteractiveExists() {
        let style: RFCardStyle = .interactive
        switch style {
        case .interactive:
            #expect(true)
        case .standard:
            #expect(Bool(false), "Interactive yerine standard geldi")
        }
    }
}
