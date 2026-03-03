import Foundation
import Testing
@testable import RafRaf

/// TTSRequest testleri.
@Suite("TTSRequest Tests")
struct TTSRequestTests {

    @Test("Request dogru olusturulabilmeli")
    func createRequest() {
        let request = TTSRequest(text: "Merhaba", voice: .alloy, speed: 1.0)

        #expect(request.text == "Merhaba")
        #expect(request.voice == .alloy)
        #expect(request.speed == 1.0)
    }

    @Test("Varsayilan hiz degeri dogru olmali")
    func defaultSpeed() {
        #expect(TTSRequest.defaultSpeed == 1.0)
    }

    @Test("Minimum hiz degeri dogru olmali")
    func minimumSpeed() {
        #expect(TTSRequest.minimumSpeed == 0.25)
    }

    @Test("Maksimum hiz degeri dogru olmali")
    func maximumSpeed() {
        #expect(TTSRequest.maximumSpeed == 4.0)
    }

    @Test("Equatable: ayni request'ler esit olmali")
    func equalRequests() {
        let request1 = TTSRequest(text: "Test", voice: .nova, speed: 1.5)
        let request2 = TTSRequest(text: "Test", voice: .nova, speed: 1.5)

        #expect(request1 == request2)
    }

    @Test("Equatable: farkli text esit olmamali")
    func differentText() {
        let request1 = TTSRequest(text: "Test 1", voice: .alloy, speed: 1.0)
        let request2 = TTSRequest(text: "Test 2", voice: .alloy, speed: 1.0)

        #expect(request1 != request2)
    }

    @Test("Equatable: farkli voice esit olmamali")
    func differentVoice() {
        let request1 = TTSRequest(text: "Test", voice: .alloy, speed: 1.0)
        let request2 = TTSRequest(text: "Test", voice: .nova, speed: 1.0)

        #expect(request1 != request2)
    }

    @Test("Equatable: farkli speed esit olmamali")
    func differentSpeed() {
        let request1 = TTSRequest(text: "Test", voice: .alloy, speed: 1.0)
        let request2 = TTSRequest(text: "Test", voice: .alloy, speed: 2.0)

        #expect(request1 != request2)
    }
}
