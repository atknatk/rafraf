import Foundation
import Testing
@testable import RafRaf

/// TTSVoice testleri.
@Suite("TTSVoice Tests")
struct TTSVoiceTests {

    @Test("Tum sesler rawValue'a sahip olmali")
    func allVoicesHaveRawValue() {
        for voice in TTSVoice.allCases {
            #expect(!voice.rawValue.isEmpty)
        }
    }

    @Test("Tum sesler displayName'e sahip olmali")
    func allVoicesHaveDisplayName() {
        for voice in TTSVoice.allCases {
            #expect(!voice.displayName.isEmpty)
        }
    }

    @Test("6 ses secenegi olmali")
    func sixVoicesAvailable() {
        #expect(TTSVoice.allCases.count == 6)
    }

    @Test("Ses rawValue'lari dogru olmali")
    func voiceRawValues() {
        #expect(TTSVoice.alloy.rawValue == "alloy")
        #expect(TTSVoice.echo.rawValue == "echo")
        #expect(TTSVoice.fable.rawValue == "fable")
        #expect(TTSVoice.onyx.rawValue == "onyx")
        #expect(TTSVoice.nova.rawValue == "nova")
        #expect(TTSVoice.shimmer.rawValue == "shimmer")
    }

    @Test("String'den TTSVoice olusturulabilmeli")
    func voiceFromString() {
        #expect(TTSVoice(rawValue: "alloy") == .alloy)
        #expect(TTSVoice(rawValue: "nova") == .nova)
        #expect(TTSVoice(rawValue: "gecersiz") == nil)
    }

    @Test("Storage key tanimli olmali")
    func storageKeyDefined() {
        #expect(!TTSVoice.storageKey.isEmpty)
        #expect(TTSVoice.storageKey == "voiceOutput.selectedVoice")
    }

    @Test("Codable: encode ve decode dogru calisir")
    func codableRoundTrip() throws {
        let voice = TTSVoice.shimmer
        let encoder = JSONEncoder()
        let decoder = JSONDecoder()

        let data = try encoder.encode(voice)
        let decoded = try decoder.decode(TTSVoice.self, from: data)

        #expect(decoded == voice)
    }
}
