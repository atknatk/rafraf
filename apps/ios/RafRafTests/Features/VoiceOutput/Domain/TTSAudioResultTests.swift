import Foundation
import Testing
@testable import RafRaf

/// TTSAudioResult testleri.
@Suite("TTSAudioResult Tests")
struct TTSAudioResultTests {

    @Test("AudioResult dogru olusturulabilmeli")
    func createAudioResult() {
        let data = Data(repeating: 0xFF, count: 512)
        let result = TTSAudioResult(
            audioData: data,
            text: "Merhaba",
            voice: .alloy,
            duration: 5.0
        )

        #expect(result.audioData == data)
        #expect(result.text == "Merhaba")
        #expect(result.voice == .alloy)
        #expect(result.duration == 5.0)
    }

    @Test("Duration opsiyonel olmali (varsayilan nil)")
    func durationOptional() {
        let result = TTSAudioResult(
            audioData: Data(),
            text: "Test",
            voice: .nova
        )

        #expect(result.duration == nil)
    }

    @Test("Equatable: ayni sonuclar esit olmali")
    func equalResults() {
        let data = Data(repeating: 0xAB, count: 100)
        let result1 = TTSAudioResult(audioData: data, text: "Test", voice: .echo, duration: 2.0)
        let result2 = TTSAudioResult(audioData: data, text: "Test", voice: .echo, duration: 2.0)

        #expect(result1 == result2)
    }

    @Test("Equatable: farkli data esit olmamali")
    func differentData() {
        let result1 = TTSAudioResult(
            audioData: Data(repeating: 0x01, count: 100),
            text: "Test",
            voice: .alloy
        )
        let result2 = TTSAudioResult(
            audioData: Data(repeating: 0x02, count: 100),
            text: "Test",
            voice: .alloy
        )

        #expect(result1 != result2)
    }

    @Test("Sendable uyumu: farkli thread'lerde kullanilabilmeli")
    func sendableConformance() async {
        let result = VoiceOutputTestFactory.createAudioResult()

        let task = Task.detached { () -> TTSAudioResult in
            return result
        }

        let taskResult = await task.value
        #expect(taskResult == result)
    }
}
