import Foundation
import Testing
@testable import RafRaf

/// VoiceInputState testleri.
@Suite("VoiceInputState Tests")
struct VoiceInputStateTests {

    @Test("idle durumu esitlik kontrolu")
    func idleEquality() {
        #expect(VoiceInputState.idle == VoiceInputState.idle)
    }

    @Test("recording durumu esitlik kontrolu")
    func recordingEquality() {
        #expect(VoiceInputState.recording == VoiceInputState.recording)
    }

    @Test("error durumlari esitlik kontrolu - ayni hata")
    func errorEqualitySameError() {
        #expect(
            VoiceInputState.error(.microphonePermissionDenied)
            == VoiceInputState.error(.microphonePermissionDenied)
        )
    }

    @Test("error durumlari esitlik kontrolu - farkli hata")
    func errorEqualityDifferentError() {
        #expect(
            VoiceInputState.error(.microphonePermissionDenied)
            != VoiceInputState.error(.networkUnavailable)
        )
    }

    @Test("farkli durumlar esit olmamali")
    func differentStatesNotEqual() {
        #expect(VoiceInputState.idle != VoiceInputState.recording)
        #expect(VoiceInputState.recording != VoiceInputState.processing)
        #expect(VoiceInputState.requesting != VoiceInputState.idle)
    }
}

/// VoiceInputError testleri.
@Suite("VoiceInputError Tests")
struct VoiceInputErrorTests {

    @Test("Her hata tipi icin localizedMessage bos olmamali")
    func localizedMessagesNotEmpty() {
        let errors: [VoiceInputError] = [
            .microphonePermissionDenied,
            .deepgramConnectionFailed,
            .networkUnavailable,
            .audioSessionError,
            .transcriptionFailed,
            .emptyTranscription,
        ]

        for error in errors {
            #expect(!error.localizedMessage.isEmpty)
        }
    }

    @Test("microphonePermissionDenied hatasi Equatable")
    func microphonePermissionEquatable() {
        #expect(VoiceInputError.microphonePermissionDenied == .microphonePermissionDenied)
        #expect(VoiceInputError.microphonePermissionDenied != .networkUnavailable)
    }
}
