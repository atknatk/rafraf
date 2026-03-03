import Foundation

/// Transkripsiyon sonucu domain modeli.
/// Deepgram'dan gelen interim veya final sonucu temsil eder.
struct TranscriptionResult: Sendable, Equatable {
    /// Transkripsiyon metni.
    let text: String
    /// Final sonuc mu (true) yoksa interim mi (false).
    let isFinal: Bool
    /// Guven skoru (0.0 - 1.0).
    let confidence: Double
    /// Transkripsiyon dili.
    let language: VoiceLanguage
}

/// Ses seviyesi verisi.
/// AVAudioEngine'den alinan ses gucu degerlerini temsil eder.
struct AudioLevel: Sendable, Equatable {
    /// Ortalama ses gucu (dB, -160 ile 0 arasi).
    let averagePower: Float
    /// Tepe ses gucu (dB, -160 ile 0 arasi).
    let peakPower: Float
    /// Normalize edilmis seviye (0.0 - 1.0).
    let normalizedLevel: Float

    /// dB degerini 0-1 araligina normalize eder.
    /// - Parameter decibels: dB degeri (-160 ile 0 arasi).
    /// - Returns: Normalize edilmis deger (0.0 - 1.0).
    static func normalize(decibels: Float) -> Float {
        // -160 dB sessizlik, 0 dB maksimum
        let minDb: Float = -60.0
        let maxDb: Float = 0.0
        let clamped = max(minDb, min(maxDb, decibels))
        return (clamped - minDb) / (maxDb - minDb)
    }
}
