import Foundation
import Testing
@testable import RafRaf

/// V1 SHIP BLOCKER regression tests: `approval_response` WebSocket envelope wire shape.
///
/// Backend `_handle_approval_response` (apps/backend/app/api/routes/websocket.py:1049)
/// requires `content` to be a JSON object (`isinstance(content, dict)`); a JSON-encoded
/// string causes the backend to emit `INVALID_APPROVAL_RESPONSE` and the awaiter to
/// time out, after which the bridge auto-denies. These tests pin the dict-shape so a
/// future refactor cannot regress to the broken `.text(jsonString)` envelope.
@Suite("Approval Response Wire Shape Tests")
struct ApprovalRepositoryWireShapeTests {

    // MARK: - Helpers

    /// Production-equivalent encode path: same JSONEncoder configuration as
    /// `WebSocketMessageRouter.encode(_:)` (no key strategy, ISO8601 dates).
    private func encodeMessage(_ message: WebSocketBaseMessage) throws -> Data {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return try encoder.encode(message)
    }

    private func makeApprovalResponseMessage(
        approvalId: String,
        decision: String,
        note: String?
    ) -> WebSocketBaseMessage {
        let dto = ApprovalResponseDTO(
            approvalId: approvalId,
            decision: decision,
            note: note
        )
        return WebSocketBaseMessage(
            type: "approval_response",
            content: .approvalResponse(dto),
            metadata: WebSocketMessageMetadata(
                direction: WebSocketMessageDirection.clientToServer.rawValue
            )
        )
    }

    // MARK: - Wire Shape

    @Test("Wire frame `content` alani DICT olmali (string DEGIL)")
    func contentIsDictNotString() throws {
        let message = makeApprovalResponseMessage(
            approvalId: "wire-1",
            decision: "approved",
            note: nil
        )

        let data = try encodeMessage(message)
        let envelope = try #require(
            try JSONSerialization.jsonObject(with: data) as? [String: Any]
        )

        // Critical assertion: backend rejects content if it's a string.
        // Old broken sender produced `content: "{\"approval_id\":...}"`.
        #expect(envelope["content"] is [String: Any], "content MUST be a dict, not a JSON-encoded string")
        #expect((envelope["content"] as? String) == nil, "content MUST NOT be a string")
    }

    @Test("Wire frame backend dict key kontratini karsilamali")
    func contentDictKeysMatchBackendContract() throws {
        let message = makeApprovalResponseMessage(
            approvalId: "wire-2",
            decision: "approved",
            note: "Allow once"
        )

        let data = try encodeMessage(message)
        let envelope = try #require(
            try JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        let content = try #require(envelope["content"] as? [String: Any])

        #expect(content["approval_id"] as? String == "wire-2")
        #expect(content["decision"] as? String == "approved")
        #expect(content["note"] as? String == "Allow once")

        // Wire keys are exactly the snake_case set the backend reads from
        // raw_data.get("content") at apps/backend/app/api/routes/websocket.py:1059-1080.
        let expectedKeys: Set<String> = ["approval_id", "decision", "note"]
        let actualKeys = Set(content.keys)
        #expect(actualKeys == expectedKeys, "Wire keys must be exactly approval_id/decision/note")
    }

    @Test("Reddedilen karar wire'a snake_case `decision: rejected` olarak yazilmali")
    func rejectedDecisionWireValue() throws {
        let message = makeApprovalResponseMessage(
            approvalId: "wire-3",
            decision: "rejected",
            note: "Tehlikeli"
        )

        let data = try encodeMessage(message)
        let envelope = try #require(
            try JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        let content = try #require(envelope["content"] as? [String: Any])

        #expect(content["decision"] as? String == "rejected")
    }

    @Test("Note nil oldugunda wire'da kabul edilebilir bir bicimde aktarilir")
    func noteNilSerializedAcceptably() throws {
        let message = makeApprovalResponseMessage(
            approvalId: "wire-4",
            decision: "approved",
            note: nil
        )

        let data = try encodeMessage(message)
        let envelope = try #require(
            try JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        let content = try #require(envelope["content"] as? [String: Any])

        // Backend `_handle_approval_response` calls `content.get("note")` — that
        // returns None if the key is missing OR present-with-null. Both are
        // acceptable; what the backend MUST NEVER see is `content` as a string.
        let noteSlot = content["note"]
        let isAbsent = (noteSlot == nil)
        let isJSONNull = noteSlot is NSNull
        #expect(isAbsent || isJSONNull, "note nil must serialize as missing key or JSON null")
    }

    @Test("Envelope type alani 'approval_response' olmali")
    func envelopeTypeIsApprovalResponse() throws {
        let message = makeApprovalResponseMessage(
            approvalId: "wire-5",
            decision: "approved",
            note: nil
        )

        let data = try encodeMessage(message)
        let envelope = try #require(
            try JSONSerialization.jsonObject(with: data) as? [String: Any]
        )

        #expect(envelope["type"] as? String == "approval_response")
    }

    // MARK: - WebSocketContent.encode

    @Test("WebSocketContent.approvalResponse encode dogrudan dict uretir")
    func webSocketContentApprovalResponseEncodesAsDict() throws {
        let dto = ApprovalResponseDTO(
            approvalId: "content-1",
            decision: "approved",
            note: nil
        )
        let content: WebSocketContent = .approvalResponse(dto)

        let data = try JSONEncoder().encode(content)
        let object = try JSONSerialization.jsonObject(with: data)

        #expect(object is [String: Any], "WebSocketContent.approvalResponse MUST encode as dict")
        let dict = try #require(object as? [String: Any])
        #expect(dict["approval_id"] as? String == "content-1")
        #expect(dict["decision"] as? String == "approved")
    }
}
