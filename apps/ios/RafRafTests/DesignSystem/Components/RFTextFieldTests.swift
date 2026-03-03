import Foundation
import Testing
@testable import RafRaf

/// RFTextField bilesen testleri.
@Suite("RFTextField Tests")
struct RFTextFieldTests {

    @Test("RFTextFieldMode tum varyantlari mevcut olmali")
    func textFieldModeVariants() {
        let modes: [RFTextFieldMode] = [.text, .secure, .multiline]
        #expect(modes.count == 3)
    }

    @Test("RFTextFieldMode text enum degeri dogru olmali")
    func textFieldModeTextExists() {
        let mode: RFTextFieldMode = .text
        switch mode {
        case .text:
            #expect(true)
        case .secure, .multiline:
            #expect(Bool(false), "Text yerine baska mod geldi")
        }
    }

    @Test("RFTextFieldMode secure enum degeri dogru olmali")
    func textFieldModeSecureExists() {
        let mode: RFTextFieldMode = .secure
        switch mode {
        case .secure:
            #expect(true)
        case .text, .multiline:
            #expect(Bool(false), "Secure yerine baska mod geldi")
        }
    }

    @Test("RFTextFieldMode multiline enum degeri dogru olmali")
    func textFieldModeMultilineExists() {
        let mode: RFTextFieldMode = .multiline
        switch mode {
        case .multiline:
            #expect(true)
        case .text, .secure:
            #expect(Bool(false), "Multiline yerine baska mod geldi")
        }
    }
}
