import Foundation

/// Deepgram DTO -> Domain model donusturucusu.
/// Data katmanindaki DTO'lari domain katmanindaki modellere cevirir.
enum TranscriptionMapper {
    /// DeepgramTranscriptDTO'yu TranscriptionResult'a donusturur.
    /// - Parameters:
    ///   - dto: Deepgram transkripsiyon DTO'su.
    ///   - language: Aktif transkripsiyon dili.
    /// - Returns: Domain model veya nil (bos transkripsiyon durumunda).
    static func toDomain(
        from dto: DeepgramTranscriptDTO,
        language: VoiceLanguage
    ) -> TranscriptionResult? {
        guard let firstAlternative = dto.channel.alternatives.first else {
            return nil
        }

        // Bos transkripsiyon kontrolu
        let text = firstAlternative.transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            return nil
        }

        return TranscriptionResult(
            text: text,
            isFinal: dto.isFinal,
            confidence: firstAlternative.confidence,
            language: language
        )
    }
}
