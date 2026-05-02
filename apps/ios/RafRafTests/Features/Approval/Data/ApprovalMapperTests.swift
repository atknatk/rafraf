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

    // MARK: - V1.5 toQuestion alias

    @Test("toQuestion(dto:) ayni davranisi sergiler (alias)")
    func toQuestion_isAliasOfToDomain() {
        let dto = ApprovalTestFactory.makeQuestionDTO(approvalId: "alias-1")
        let viaAlias = ApprovalMapper.toQuestion(dto: dto)
        let viaCanonical = ApprovalMapper.toDomain(dto)

        #expect(viaAlias.id == viaCanonical.id)
        #expect(viaAlias.question == viaCanonical.question)
        #expect(viaAlias.category == viaCanonical.category)
    }

    // MARK: - V1.5 toSheetRequest

    @Test("toSheetRequest destructive kategori -> high risk policy")
    func toSheetRequest_destructiveCategoryHighRisk() {
        let q = ApprovalTestFactory.makeQuestion(
            id: "sheet-1",
            question: "rm -rf /tmp/x",
            context: "Tool: Bash, Action: rm -rf /tmp/x",
            category: .destructive,
            receivedAt: Date()
        )

        let req = ApprovalMapper.toSheetRequest(question: q)

        #expect(req.id == "sheet-1")
        #expect(req.toolName == "Bash")
        #expect(req.inputPreview == "rm -rf /tmp/x")
        #expect(req.policy == .prompt(risk: .high))
    }

    @Test("toSheetRequest infrastructure kategori -> medium risk policy")
    func toSheetRequest_infrastructureCategoryMediumRisk() {
        let q = ApprovalTestFactory.makeQuestion(
            id: "sheet-2",
            context: "Tool: Edit, Action: change config",
            category: .infrastructure
        )

        let req = ApprovalMapper.toSheetRequest(question: q)

        #expect(req.policy == .prompt(risk: .medium))
        #expect(req.toolName == "Edit")
    }

    @Test("toSheetRequest writeRemote kategori -> medium risk policy")
    func toSheetRequest_writeRemoteCategoryMediumRisk() {
        let q = ApprovalTestFactory.makeQuestion(
            id: "sheet-3",
            context: nil,
            category: .writeRemote
        )

        let req = ApprovalMapper.toSheetRequest(question: q)

        #expect(req.policy == .prompt(risk: .medium))
        // context nil -> default label fallback
        #expect(req.toolName == "Remote Write")
    }

    @Test("toSheetRequest deploy kategori -> high risk policy")
    func toSheetRequest_deployCategoryHighRisk() {
        let q = ApprovalTestFactory.makeQuestion(
            id: "sheet-4",
            context: "Tool: Deploy, Action: roll out v1.0",
            category: .deploy
        )

        let req = ApprovalMapper.toSheetRequest(question: q)

        #expect(req.policy == .prompt(risk: .high))
    }

    @Test("toSheetRequest timeout backend'den propagate edilir")
    func toSheetRequest_propagatesTimeout() {
        let q = ApprovalTestFactory.makeQuestion(
            id: "sheet-5",
            timeoutSeconds: 30,
            category: .destructive
        )

        let req = ApprovalMapper.toSheetRequest(question: q)

        #expect(req.timeoutSeconds == 30)
    }

    @Test("parseToolName 'Tool: <X>, Action: ...' formatini ayristirir")
    func parseToolName_extractsTool() {
        let result = ApprovalMapper.parseToolName(fromContext: "Tool: WebFetch, Action: GET https://api.example.com")
        #expect(result == "WebFetch")
    }

    @Test("parseToolName tool prefix yoksa nil doner")
    func parseToolName_returnsNilWithoutPrefix() {
        #expect(ApprovalMapper.parseToolName(fromContext: "image=foo:1.0.0") == nil)
        #expect(ApprovalMapper.parseToolName(fromContext: nil) == nil)
        #expect(ApprovalMapper.parseToolName(fromContext: "") == nil)
    }
}
