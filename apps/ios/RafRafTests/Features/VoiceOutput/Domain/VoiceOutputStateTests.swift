import Foundation
import Testing
@testable import RafRaf

/// VoiceOutputState testleri.
@Suite("VoiceOutputState Tests")
struct VoiceOutputStateTests {

    // MARK: - Equatable

    @Test("Ayni durumlar esit olmali")
    func sameStatesEqual() {
        #expect(VoiceOutputState.idle == VoiceOutputState.idle)
        #expect(VoiceOutputState.loading == VoiceOutputState.loading)
        #expect(VoiceOutputState.playing == VoiceOutputState.playing)
        #expect(VoiceOutputState.paused == VoiceOutputState.paused)
    }

    @Test("Farkli durumlar esit olmamali")
    func differentStatesNotEqual() {
        #expect(VoiceOutputState.idle != VoiceOutputState.loading)
        #expect(VoiceOutputState.playing != VoiceOutputState.paused)
        #expect(VoiceOutputState.loading != VoiceOutputState.playing)
    }

    @Test("Ayni hata tipleri esit olmali")
    func sameErrorStatesEqual() {
        #expect(
            VoiceOutputState.error(.ttsRequestFailed) == VoiceOutputState.error(.ttsRequestFailed)
        )
        #expect(
            VoiceOutputState.error(.playbackFailed) == VoiceOutputState.error(.playbackFailed)
        )
    }

    @Test("Farkli hata tipleri esit olmamali")
    func differentErrorStatesNotEqual() {
        #expect(
            VoiceOutputState.error(.ttsRequestFailed) != VoiceOutputState.error(.playbackFailed)
        )
    }

    // MARK: - VoiceOutputError

    @Test("Tum hata tipleri lokalize mesaj donmeli")
    func allErrorsHaveLocalizedMessage() {
        let errors: [VoiceOutputError] = [
            .ttsRequestFailed,
            .audioDecodingFailed,
            .playbackFailed,
            .networkUnavailable,
            .emptyText,
        ]

        for error in errors {
            #expect(!error.localizedMessage.isEmpty)
        }
    }

    @Test("emptyText hatasi dogru mesaj donmeli")
    func emptyTextErrorMessage() {
        let error = VoiceOutputError.emptyText
        #expect(!error.localizedMessage.isEmpty)
    }
}
