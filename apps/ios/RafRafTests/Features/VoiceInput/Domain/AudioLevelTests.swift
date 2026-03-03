import Foundation
import Testing
@testable import RafRaf

/// AudioLevel testleri.
@Suite("AudioLevel Tests")
struct AudioLevelTests {

    @Test("normalize: -60 dB -> 0.0")
    func normalizeSilence() {
        let result = AudioLevel.normalize(decibels: -60.0)
        #expect(result == 0.0)
    }

    @Test("normalize: 0 dB -> 1.0")
    func normalizeMaximum() {
        let result = AudioLevel.normalize(decibels: 0.0)
        #expect(result == 1.0)
    }

    @Test("normalize: -30 dB -> 0.5")
    func normalizeMidpoint() {
        let result = AudioLevel.normalize(decibels: -30.0)
        #expect(abs(result - 0.5) < 0.01)
    }

    @Test("normalize: -160 dB clamped to 0.0 (min -60 dB)")
    func normalizeClampedLow() {
        let result = AudioLevel.normalize(decibels: -160.0)
        #expect(result == 0.0)
    }

    @Test("normalize: 10 dB clamped to 1.0 (max 0 dB)")
    func normalizeClampedHigh() {
        let result = AudioLevel.normalize(decibels: 10.0)
        #expect(result == 1.0)
    }

    @Test("normalize: sonuc her zaman 0-1 arasinda")
    func normalizeRange() {
        let testValues: [Float] = [-200, -100, -60, -50, -30, -10, 0, 5, 20]
        for db in testValues {
            let result = AudioLevel.normalize(decibels: db)
            #expect(result >= 0.0)
            #expect(result <= 1.0)
        }
    }

    @Test("AudioLevel Equatable")
    func equatable() {
        let level1 = AudioLevel(averagePower: -20, peakPower: -10, normalizedLevel: 0.67)
        let level2 = AudioLevel(averagePower: -20, peakPower: -10, normalizedLevel: 0.67)
        let level3 = AudioLevel(averagePower: -30, peakPower: -10, normalizedLevel: 0.5)

        #expect(level1 == level2)
        #expect(level1 != level3)
    }

    @Test("AudioLevel Sendable uyumlulugu")
    func sendable() async {
        let level = AudioLevel(averagePower: -20, peakPower: -10, normalizedLevel: 0.67)
        let result = await Task { level }.value
        #expect(result == level)
    }
}
