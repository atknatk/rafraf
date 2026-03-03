import Foundation

/// Onay DTO <-> Domain model mapper.
enum ApprovalMapper {

    /// ApprovalQuestionDTO -> ApprovalQuestion domain modeline donusturur.
    /// - Parameter dto: WebSocket'ten alinan DTO
    /// - Returns: Domain modeli
    static func toDomain(_ dto: ApprovalQuestionDTO) -> ApprovalQuestion {
        ApprovalQuestion(
            id: dto.approvalId,
            question: dto.question,
            context: dto.context,
            options: dto.options.map { optionToDomain($0) },
            timeoutSeconds: dto.timeoutSeconds,
            category: ApprovalCategory(rawValue: dto.category) ?? .destructive,
            receivedAt: Date()
        )
    }

    /// ApprovalOptionDTO -> ApprovalOption domain modeline donusturur.
    /// - Parameter dto: Secenek DTO
    /// - Returns: Domain modeli
    static func optionToDomain(_ dto: ApprovalOptionDTO) -> ApprovalOption {
        ApprovalOption(
            id: dto.id,
            label: dto.label,
            style: ApprovalOptionStyle(rawValue: dto.style) ?? .secondary
        )
    }

    /// Domain karar bilgisini ApprovalResponseDTO'ya donusturur.
    /// - Parameters:
    ///   - approvalId: Onay talebi ID'si
    ///   - decision: Kullanici karari
    ///   - note: Kullanici notu
    /// - Returns: WebSocket'e gonderilecek DTO
    static func toResponseDTO(
        approvalId: String,
        decision: ApprovalDecision,
        note: String?
    ) -> ApprovalResponseDTO {
        ApprovalResponseDTO(
            approvalId: approvalId,
            decision: decision.rawValue,
            note: note
        )
    }
}
