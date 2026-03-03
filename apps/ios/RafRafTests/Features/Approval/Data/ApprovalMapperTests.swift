import Foundation
import Testing
@testable import RafRaf

/// ApprovalMapper testleri.
@Suite("ApprovalMapper Tests")
struct ApprovalMapperTests {

    // MARK: - toDomain

    @Test("ApprovalQuestionDTO domain modeline dogru donusturulmeli")
    func toDomainBasic() {
        let dto = ApprovalTestFactory.makeQuestionDTO()
        let domain = ApprovalMapper.toDomain(dto)

        #expect(domain.id == dto.approvalId)
        #expect(domain.question == dto.question)
        #expect(domain.context == dto.context)
        #expect(domain.timeoutSeconds == dto.timeoutSeconds)
        #expect(domain.category == .deploy)
        #expect(domain.options.count == dto.options.count)
    }

    @Test("Secenekler dogru style ile map edilmeli")
    func toDomainOptionStyles() {
        let dto = ApprovalTestFactory.makeQuestionDTO(
            options: [
                ApprovalOptionDTO(id: "a", label: "Primary", style: "primary"),
                ApprovalOptionDTO(id: "b", label: "Danger", style: "danger"),
                ApprovalOptionDTO(id: "c", label: "Secondary", style: "secondary")
            ]
        )

        let domain = ApprovalMapper.toDomain(dto)

        #expect(domain.options[0].style == .primary)
        #expect(domain.options[1].style == .danger)
        #expect(domain.options[2].style == .secondary)
    }

    @Test("Bilinmeyen kategori destructive olarak map edilmeli")
    func toDomainUnknownCategory() {
        let dto = ApprovalTestFactory.makeQuestionDTO(category: "unknown_category")
        let domain = ApprovalMapper.toDomain(dto)

        #expect(domain.category == .destructive)
    }

    @Test("Bilinmeyen option style secondary olarak map edilmeli")
    func toDomainUnknownOptionStyle() {
        let dto = ApprovalTestFactory.makeQuestionDTO(
            options: [
                ApprovalOptionDTO(id: "x", label: "Unknown", style: "unknown_style")
            ]
        )

        let domain = ApprovalMapper.toDomain(dto)

        #expect(domain.options[0].style == .secondary)
    }

    @Test("Context nil oldugunda nil olarak map edilmeli")
    func toDomainNilContext() {
        let dto = ApprovalTestFactory.makeQuestionDTO(context: nil)
        let domain = ApprovalMapper.toDomain(dto)

        #expect(domain.context == nil)
    }

    @Test("write_remote kategorisi dogru map edilmeli")
    func toDomainWriteRemoteCategory() {
        let dto = ApprovalTestFactory.makeQuestionDTO(category: "write_remote")
        let domain = ApprovalMapper.toDomain(dto)

        #expect(domain.category == .writeRemote)
    }

    @Test("receivedAt mevcut zamana yakin olmali")
    func toDomainReceivedAt() {
        let before = Date()
        let dto = ApprovalTestFactory.makeQuestionDTO()
        let domain = ApprovalMapper.toDomain(dto)
        let after = Date()

        #expect(domain.receivedAt >= before)
        #expect(domain.receivedAt <= after)
    }

    // MARK: - toResponseDTO

    @Test("Approved karar dogru DTO'ya donusturulmeli")
    func toResponseDTOApproved() {
        let dto = ApprovalMapper.toResponseDTO(
            approvalId: "test-123",
            decision: .approved,
            note: nil
        )

        #expect(dto.approvalId == "test-123")
        #expect(dto.decision == "approved")
        #expect(dto.note == nil)
    }

    @Test("Rejected karar note ile dogru DTO'ya donusturulmeli")
    func toResponseDTORejectedWithNote() {
        let dto = ApprovalMapper.toResponseDTO(
            approvalId: "test-456",
            decision: .rejected,
            note: "Timeout - otomatik red"
        )

        #expect(dto.approvalId == "test-456")
        #expect(dto.decision == "rejected")
        #expect(dto.note == "Timeout - otomatik red")
    }
}
