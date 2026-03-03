import Foundation

/// Deepgram transkripsiyon sonuc DTO'su.
/// Deepgram WebSocket API'dan gelen JSON mesajini temsil eder.
struct DeepgramTranscriptDTO: Codable, Sendable {
    /// Mesaj tipi ("Results").
    let type: String
    /// Kanal indeksi.
    let channelIndex: [Int]?
    /// Ses suresi (saniye).
    let duration: Double?
    /// Baslangic zamani (saniye).
    let start: Double?
    /// Final sonuc mu.
    let isFinal: Bool
    /// Konusma sonu tespit edildi mi.
    let speechFinal: Bool
    /// Kanal transkripsiyon verisi.
    let channel: DeepgramChannelDTO

    enum CodingKeys: String, CodingKey {
        case type
        case channelIndex = "channel_index"
        case duration
        case start
        case isFinal = "is_final"
        case speechFinal = "speech_final"
        case channel
    }
}

/// Deepgram kanal verisi.
struct DeepgramChannelDTO: Codable, Sendable {
    /// Alternatif transkripsiyon sonuclari (en yuksek guvenli ilk sirada).
    let alternatives: [DeepgramAlternativeDTO]
}

/// Deepgram alternatif transkripsiyon.
struct DeepgramAlternativeDTO: Codable, Sendable {
    /// Transkripsiyon metni.
    let transcript: String
    /// Guven skoru (0-1).
    let confidence: Double
    /// Kelime bazli detay (opsiyonel).
    let words: [DeepgramWordDTO]?
}

/// Deepgram kelime detayi.
struct DeepgramWordDTO: Codable, Sendable {
    /// Kelime.
    let word: String
    /// Kelime baslangic zamani (saniye).
    let start: Double
    /// Kelime bitis zamani (saniye).
    let end: Double
    /// Kelime guven skoru.
    let confidence: Double
    /// Noktali kelime (opsiyonel).
    let punctuatedWord: String?

    enum CodingKeys: String, CodingKey {
        case word, start, end, confidence
        case punctuatedWord = "punctuated_word"
    }
}

/// Deepgram metadata mesaji (ilk baglanti cevabi).
struct DeepgramMetadataDTO: Codable, Sendable {
    /// Mesaj tipi ("Metadata").
    let type: String
    /// İstek ID'si.
    let requestId: String?
    /// Model bilgisi.
    let modelInfo: DeepgramModelInfoDTO?

    enum CodingKeys: String, CodingKey {
        case type
        case requestId = "request_id"
        case modelInfo = "model_info"
    }
}

/// Deepgram model bilgisi.
struct DeepgramModelInfoDTO: Codable, Sendable {
    /// Model adi.
    let name: String?
    /// Model versiyonu.
    let version: String?
}

/// Deepgram stream kapatma mesaji.
struct DeepgramCloseStreamDTO: Codable, Sendable {
    /// Mesaj tipi ("CloseStream").
    let type: String

    init() {
        self.type = "CloseStream"
    }
}
