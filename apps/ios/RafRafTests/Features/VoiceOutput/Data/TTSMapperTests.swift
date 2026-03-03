import Foundation
import Testing
@testable import RafRaf

/// TTSMapper testleri.
@Suite("TTSMapper Tests")
struct TTSMapperTests {

    // MARK: - toDTO

    @Test("toDTO: domain request'i DTO'ya dogru donusturmeli")
    func toDTOConversion() {
        let request = VoiceOutputTestFactory.createRequest(
            text: "Merhaba dunya",
            voice: .nova,
            speed: 1.5
        )

        let dto = TTSMapper.toDTO(from: request)

        #expect(dto.text == "Merhaba dunya")
        #expect(dto.voice == "nova")
        #expect(dto.speed == 1.5)
    }

    @Test("toDTO: tum ses tiplerini dogru eslestirmeli")
    func toDTOAllVoices() {
        for voice in TTSVoice.allCases {
            let request = VoiceOutputTestFactory.createRequest(voice: voice)
            let dto = TTSMapper.toDTO(from: request)
            #expect(dto.voice == voice.rawValue)
        }
    }

    @Test("toDTO: hiz degerlerini koruyor olmali")
    func toDTOSpeedValues() {
        let speeds: [Double] = [0.25, 0.5, 1.0, 1.5, 2.0, 4.0]

        for speed in speeds {
            let request = VoiceOutputTestFactory.createRequest(speed: speed)
            let dto = TTSMapper.toDTO(from: request)
            #expect(dto.speed == speed)
        }
    }

    // MARK: - toDomain

    @Test("toDomain: ses verisini domain modele donusturmeli")
    func toDomainConversion() {
        let data = Data(repeating: 0xAB, count: 512)
        let request = VoiceOutputTestFactory.createRequest(
            text: "Test metni",
            voice: .echo
        )

        let result = TTSMapper.toDomain(from: data, request: request)

        #expect(result.audioData == data)
        #expect(result.text == "Test metni")
        #expect(result.voice == .echo)
        #expect(result.duration == nil)
    }

    @Test("toDomain: bos data ile de calismali")
    func toDomainEmptyData() {
        let request = VoiceOutputTestFactory.createRequest()
        let result = TTSMapper.toDomain(from: Data(), request: request)

        #expect(result.audioData.isEmpty)
    }

    @Test("toDomain: buyuk data ile de calismali")
    func toDomainLargeData() {
        let largeData = VoiceOutputTestFactory.largeAudioData
        let request = VoiceOutputTestFactory.createRequest()
        let result = TTSMapper.toDomain(from: largeData, request: request)

        #expect(result.audioData.count == 1024 * 1024)
    }
}
