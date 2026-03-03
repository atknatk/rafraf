import Foundation
import Testing
@testable import RafRaf

/// NotificationRouter deep link parsing testleri.
@Suite("NotificationRouter Tests")
struct NotificationRouterTests {

    // MARK: - Chat Deep Links

    @Test("Chat deep link dogru parse edilmeli")
    func chatDeepLink() {
        let result = NotificationRouter.destination(from: "rafraf://chat/session-123")
        #expect(result == .chat(sessionId: "session-123"))
    }

    @Test("Chat deep link session ID olmadan")
    func chatDeepLinkNoSessionId() {
        let result = NotificationRouter.destination(from: "rafraf://chat")
        #expect(result == .chat(sessionId: ""))
    }

    // MARK: - Approval Deep Links

    @Test("Approval deep link dogru parse edilmeli")
    func approvalDeepLink() {
        let result = NotificationRouter.destination(from: "rafraf://approval/apr-456")
        #expect(result == .approval(approvalId: "apr-456"))
    }

    @Test("Approval deep link ID olmadan nil donmeli")
    func approvalDeepLinkNoId() {
        let result = NotificationRouter.destination(from: "rafraf://approval")
        #expect(result == nil)
    }

    // MARK: - Project Deep Links

    @Test("Project deep link dogru parse edilmeli")
    func projectDeepLink() {
        let result = NotificationRouter.destination(from: "rafraf://project/proj-789")
        #expect(result == .project(projectId: "proj-789"))
    }

    @Test("Project deep link ID olmadan nil donmeli")
    func projectDeepLinkNoId() {
        let result = NotificationRouter.destination(from: "rafraf://project")
        #expect(result == nil)
    }

    // MARK: - Settings Deep Link

    @Test("Settings deep link dogru parse edilmeli")
    func settingsDeepLink() {
        let result = NotificationRouter.destination(from: "rafraf://settings")
        #expect(result == .settings)
    }

    // MARK: - Edge Cases

    @Test("nil deep link nil donmeli")
    func nilDeepLink() {
        let result = NotificationRouter.destination(from: nil as String?)
        #expect(result == nil)
    }

    @Test("Bos string nil donmeli")
    func emptyString() {
        let result = NotificationRouter.destination(from: "")
        #expect(result == nil)
    }

    @Test("Bilinmeyen scheme nil donmeli")
    func unknownScheme() {
        let result = NotificationRouter.destination(from: "https://example.com/chat/123")
        #expect(result == nil)
    }

    @Test("Bilinmeyen host nil donmeli")
    func unknownHost() {
        let result = NotificationRouter.destination(from: "rafraf://unknown/123")
        #expect(result == nil)
    }

    @Test("Gecersiz URL nil donmeli")
    func invalidURL() {
        let result = NotificationRouter.destination(from: "not a valid url at all")
        #expect(result == nil)
    }
}
