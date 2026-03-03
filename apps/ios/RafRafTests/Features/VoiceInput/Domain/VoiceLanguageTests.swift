import Foundation
import Testing
@testable import RafRaf

/// VoiceLanguage testleri.
@Suite("VoiceLanguage Tests")
struct VoiceLanguageTests {

    @Test("Turkish rawValue 'tr' olmali")
    func turkishRawValue() {
        #expect(VoiceLanguage.turkish.rawValue == "tr")
    }

    @Test("English rawValue 'en' olmali")
    func englishRawValue() {
        #expect(VoiceLanguage.english.rawValue == "en")
    }

    @Test("deepgramCode rawValue ile ayni olmali")
    func deepgramCode() {
        for language in VoiceLanguage.allCases {
            #expect(language.deepgramCode == language.rawValue)
        }
    }

    @Test("allCases 2 dil icermeli")
    func allCases() {
        #expect(VoiceLanguage.allCases.count == 2)
        #expect(VoiceLanguage.allCases.contains(.turkish))
        #expect(VoiceLanguage.allCases.contains(.english))
    }

    @Test("defaultLanguage Turkce olmali")
    func defaultLanguage() {
        #expect(VoiceLanguage.defaultLanguage == .turkish)
    }

    @Test("displayName bos olmamali")
    func displayNameNotEmpty() {
        for language in VoiceLanguage.allCases {
            #expect(!language.displayName.isEmpty)
        }
    }

    @Test("storageKey dogru prefix'e sahip olmali")
    func storageKey() {
        #expect(VoiceLanguage.storageKey.hasPrefix("com.rafraf."))
    }

    @Test("rawValue'dan olusturma basarili olmali")
    func initFromRawValue() {
        #expect(VoiceLanguage(rawValue: "tr") == .turkish)
        #expect(VoiceLanguage(rawValue: "en") == .english)
        #expect(VoiceLanguage(rawValue: "fr") == nil)
    }
}
