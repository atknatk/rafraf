import Foundation
@testable import RafRaf

/// Approval test verisi fabrikasi.
enum ApprovalTestFactory {

    /// Standart onay sorusu olusturur.
    static func makeQuestion(
        id: String = "test-approval-123",
        question: String = "Deploy onaylansn mi?",
        context: String? = "Image: rafraf:v1.0.0",
        options: [ApprovalOption]? = nil,
        timeoutSeconds: Int = 30,
        category: ApprovalCategory = .deploy,
        receivedAt: Date = Date()
    ) -> ApprovalQuestion {
        ApprovalQuestion(
            id: id,
            question: question,
            context: context,
            options: options ?? makeDefaultOptions(),
            timeoutSeconds: timeoutSeconds,
            category: category,
            receivedAt: receivedAt
        )
    }

    /// Varsayilan secenek listesi olusturur (Onayla + Reddet).
    static func makeDefaultOptions() -> [ApprovalOption] {
        [
            ApprovalOption(id: "approve", label: "Onayla", style: .primary),
            ApprovalOption(id: "reject", label: "Reddet", style: .danger)
        ]
    }

    /// Multi-choice secenek listesi olusturur (Onayla + Detay + Reddet).
    static func makeMultiChoiceOptions() -> [ApprovalOption] {
        [
            ApprovalOption(id: "approve", label: "Onayla", style: .primary),
            ApprovalOption(id: "detail", label: "Detay Gor", style: .secondary),
            ApprovalOption(id: "reject", label: "Reddet", style: .danger)
        ]
    }

    /// ApprovalQuestionDTO olusturur.
    static func makeQuestionDTO(
        approvalId: String = "test-approval-123",
        question: String = "Deploy onaylansn mi?",
        context: String? = "Image: rafraf:v1.0.0",
        options: [ApprovalOptionDTO]? = nil,
        timeoutSeconds: Int = 30,
        category: String = "deploy"
    ) -> ApprovalQuestionDTO {
        ApprovalQuestionDTO(
            approvalId: approvalId,
            question: question,
            context: context,
            options: options ?? makeDefaultOptionDTOs(),
            timeoutSeconds: timeoutSeconds,
            category: category
        )
    }

    /// Varsayilan secenek DTO listesi olusturur.
    static func makeDefaultOptionDTOs() -> [ApprovalOptionDTO] {
        [
            ApprovalOptionDTO(id: "approve", label: "Onayla", style: "primary"),
            ApprovalOptionDTO(id: "reject", label: "Reddet", style: "danger")
        ]
    }
}
