import Foundation
import Testing
@testable import RafRaf

/// Approval domain model testleri.
@Suite("Approval Domain Model Tests")
struct ApprovalModelTests {

    // MARK: - ApprovalQuestion

    @Test("ApprovalQuestion dogru olusturulmali")
    func approvalQuestionInit() {
        let now = Date()
        let question = ApprovalQuestion(
            id: "q-123",
            question: "Deploy?",
            context: "v1.0.0",
            options: ApprovalTestFactory.makeDefaultOptions(),
            timeoutSeconds: 30,
            category: .deploy,
            receivedAt: now
        )

        #expect(question.id == "q-123")
        #expect(question.question == "Deploy?")
        #expect(question.context == "v1.0.0")
        #expect(question.options.count == 2)
        #expect(question.timeoutSeconds == 30)
        #expect(question.category == .deploy)
        #expect(question.receivedAt == now)
    }

    @Test("ApprovalQuestion Equatable uyumlu olmali")
    func approvalQuestionEquatable() {
        let now = Date()
        let options = ApprovalTestFactory.makeDefaultOptions()
        let q1 = ApprovalQuestion(
            id: "same-id", question: "Q?", context: nil,
            options: options, timeoutSeconds: 30,
            category: .deploy, receivedAt: now
        )
        let q2 = ApprovalQuestion(
            id: "same-id", question: "Q?", context: nil,
            options: options, timeoutSeconds: 30,
            category: .deploy, receivedAt: now
        )

        #expect(q1 == q2)
    }

    @Test("ApprovalQuestion farkli id ile farkli olmali")
    func approvalQuestionNotEqual() {
        let now = Date()
        let options = ApprovalTestFactory.makeDefaultOptions()
        let q1 = ApprovalQuestion(
            id: "id-1", question: "Q?", context: nil,
            options: options, timeoutSeconds: 30,
            category: .deploy, receivedAt: now
        )
        let q2 = ApprovalQuestion(
            id: "id-2", question: "Q?", context: nil,
            options: options, timeoutSeconds: 30,
            category: .deploy, receivedAt: now
        )

        #expect(q1 != q2)
    }

    // MARK: - ApprovalOption

    @Test("ApprovalOption dogru olusturulmali")
    func approvalOptionInit() {
        let option = ApprovalOption(
            id: "approve",
            label: "Onayla",
            style: .primary
        )

        #expect(option.id == "approve")
        #expect(option.label == "Onayla")
        #expect(option.style == .primary)
    }

    @Test("ApprovalOption Equatable uyumlu olmali")
    func approvalOptionEquatable() {
        let o1 = ApprovalOption(id: "x", label: "L", style: .danger)
        let o2 = ApprovalOption(id: "x", label: "L", style: .danger)

        #expect(o1 == o2)
    }

    // MARK: - ApprovalCategory

    @Test("ApprovalCategory raw value'lari dogru olmali")
    func approvalCategoryRawValues() {
        #expect(ApprovalCategory.deploy.rawValue == "deploy")
        #expect(ApprovalCategory.destructive.rawValue == "destructive")
        #expect(ApprovalCategory.infrastructure.rawValue == "infrastructure")
        #expect(ApprovalCategory.writeRemote.rawValue == "write_remote")
    }

    @Test("ApprovalCategory CaseIterable 4 case icermeli")
    func approvalCategoryAllCases() {
        #expect(ApprovalCategory.allCases.count == 4)
    }

    // MARK: - ApprovalOptionStyle

    @Test("ApprovalOptionStyle raw value'lari dogru olmali")
    func approvalOptionStyleRawValues() {
        #expect(ApprovalOptionStyle.primary.rawValue == "primary")
        #expect(ApprovalOptionStyle.danger.rawValue == "danger")
        #expect(ApprovalOptionStyle.secondary.rawValue == "secondary")
    }

    @Test("ApprovalOptionStyle CaseIterable 3 case icermeli")
    func approvalOptionStyleAllCases() {
        #expect(ApprovalOptionStyle.allCases.count == 3)
    }

    // MARK: - ApprovalDecision

    @Test("ApprovalDecision raw value'lari dogru olmali")
    func approvalDecisionRawValues() {
        #expect(ApprovalDecision.approved.rawValue == "approved")
        #expect(ApprovalDecision.rejected.rawValue == "rejected")
    }
}
