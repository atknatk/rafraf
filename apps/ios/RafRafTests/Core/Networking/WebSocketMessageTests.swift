import Foundation
import Testing
@testable import RafRaf

/// WebSocket mesaj encode/decode testleri.
@Suite("WebSocketMessage Tests")
struct WebSocketMessageTests {

    // MARK: - BaseMessage

    @Test("BaseMessage varsayilan degerlerle olusturulabilmeli")
    func baseMessageDefaultInit() {
        let message = WebSocketBaseMessage(type: "text")

        #expect(!message.id.isEmpty)
        #expect(message.type == "text")
        #expect(message.content == nil)
        #expect(message.metadata == nil)
        #expect(message.attachments == nil)
    }

    @Test("BaseMessage tum alanlarla olusturulabilmeli")
    func baseMessageFullInit() {
        let metadata = WebSocketMessageMetadata(
            sessionId: "session-123",
            direction: "client_to_server"
        )
        let message = WebSocketBaseMessage(
            id: "test-id",
            type: "text",
            content: .text("Hello"),
            metadata: metadata
        )

        #expect(message.id == "test-id")
        #expect(message.type == "text")
        #expect(message.metadata?.sessionId == "session-123")
    }

    // MARK: - Text Content Encode/Decode

    @Test("Text content dogru encode/decode edilmeli")
    func textContentEncodeDecode() throws {
        let original = WebSocketBaseMessage(
            id: "msg-1",
            type: "text",
            content: .text("Merhaba dunya")
        )

        let encoder = JSONEncoder()
        let data = try encoder.encode(original)

        let decoder = JSONDecoder()
        let decoded = try decoder.decode(WebSocketBaseMessage.self, from: data)

        #expect(decoded.id == "msg-1")
        #expect(decoded.type == "text")

        if case .text(let text) = decoded.content {
            #expect(text == "Merhaba dunya")
        } else {
            Issue.record("Content text olmali")
        }
    }

    // MARK: - ConnectionAck Content

    @Test("ConnectionAck content dogru decode edilmeli")
    func connectionAckDecode() throws {
        let json = """
        {
            "id": "ack-1",
            "type": "connection_ack",
            "content": {
                "user_id": "user-123",
                "session_id": "sess-456",
                "server_time": "2026-03-03T10:00:00Z"
            }
        }
        """

        let decoder = JSONDecoder()
        let data = json.data(using: .utf8)!
        let message = try decoder.decode(WebSocketBaseMessage.self, from: data)

        #expect(message.type == "connection_ack")

        if case .connectionAck(let ack) = message.content {
            #expect(ack.userId == "user-123")
            #expect(ack.sessionId == "sess-456")
            #expect(ack.serverTime == "2026-03-03T10:00:00Z")
        } else {
            Issue.record("Content connectionAck olmali")
        }
    }

    // MARK: - Error Content

    @Test("Error content tum alanlarla decode edilmeli")
    func errorContentDecode() throws {
        let json = """
        {
            "id": "err-1",
            "type": "error",
            "content": {
                "error_code": "AUTH_FAILED",
                "message": "Token gecersiz",
                "recoverable": true,
                "details": "JWT expired",
                "suggestion": "Yeniden giris yapin"
            }
        }
        """

        let decoder = JSONDecoder()
        let data = json.data(using: .utf8)!
        let message = try decoder.decode(WebSocketBaseMessage.self, from: data)

        if case .error(let error) = message.content {
            #expect(error.errorCode == "AUTH_FAILED")
            #expect(error.message == "Token gecersiz")
            #expect(error.recoverable == true)
            #expect(error.details == "JWT expired")
            #expect(error.suggestion == "Yeniden giris yapin")
        } else {
            Issue.record("Content error olmali")
        }
    }

    @Test("Error content opsiyonel alanlar olmadan decode edilmeli")
    func errorContentMinimalDecode() throws {
        let json = """
        {
            "id": "err-2",
            "type": "error",
            "content": {
                "error_code": "UNKNOWN",
                "message": "Bilinmeyen hata",
                "recoverable": false
            }
        }
        """

        let decoder = JSONDecoder()
        let data = json.data(using: .utf8)!
        let message = try decoder.decode(WebSocketBaseMessage.self, from: data)

        if case .error(let error) = message.content {
            #expect(error.errorCode == "UNKNOWN")
            #expect(error.recoverable == false)
            #expect(error.details == nil)
            #expect(error.suggestion == nil)
        } else {
            Issue.record("Content error olmali")
        }
    }

    // MARK: - Progress Content

    @Test("Progress content dogru decode edilmeli")
    func progressContentDecode() throws {
        let json = """
        {
            "id": "prog-1",
            "type": "progress",
            "content": {
                "task": "Kod analiz ediliyor",
                "step": 3,
                "total_steps": 10,
                "percentage": 30,
                "details": "Dosya taranıyor"
            }
        }
        """

        let decoder = JSONDecoder()
        let data = json.data(using: .utf8)!
        let message = try decoder.decode(WebSocketBaseMessage.self, from: data)

        if case .progress(let progress) = message.content {
            #expect(progress.task == "Kod analiz ediliyor")
            #expect(progress.step == 3)
            #expect(progress.totalSteps == 10)
            #expect(progress.percentage == 30)
            #expect(progress.details == "Dosya taranıyor")
        } else {
            Issue.record("Content progress olmali")
        }
    }

    // MARK: - Heartbeat Content

    @Test("Heartbeat content dogru encode/decode edilmeli")
    func heartbeatContentEncodeDecode() throws {
        let heartbeat = HeartbeatContent(timestamp: "2026-03-03T10:00:00Z")
        let original = WebSocketBaseMessage(
            id: "hb-1",
            type: "ping",
            content: .heartbeat(heartbeat)
        )

        let encoder = JSONEncoder()
        let data = try encoder.encode(original)

        let decoder = JSONDecoder()
        let decoded = try decoder.decode(WebSocketBaseMessage.self, from: data)

        if case .heartbeat(let hb) = decoded.content {
            #expect(hb.timestamp == "2026-03-03T10:00:00Z")
        } else {
            Issue.record("Content heartbeat olmali")
        }
    }

    // MARK: - Metadata

    @Test("Metadata tum alanlarla encode/decode edilmeli")
    func metadataFullEncodeDecode() throws {
        let metadata = WebSocketMessageMetadata(
            timestamp: "2026-03-03T10:00:00Z",
            sessionId: "sess-1",
            projectId: "proj-1",
            messageId: "msg-1",
            direction: "client_to_server"
        )

        let encoder = JSONEncoder()
        let data = try encoder.encode(metadata)

        let decoder = JSONDecoder()
        let decoded = try decoder.decode(WebSocketMessageMetadata.self, from: data)

        #expect(decoded.timestamp == "2026-03-03T10:00:00Z")
        #expect(decoded.sessionId == "sess-1")
        #expect(decoded.projectId == "proj-1")
        #expect(decoded.messageId == "msg-1")
        #expect(decoded.direction == "client_to_server")
    }

    @Test("Metadata opsiyonel alanlar olmadan decode edilmeli")
    func metadataMinimalDecode() throws {
        let json = """
        {
            "timestamp": "2026-03-03T10:00:00Z",
            "direction": "server_to_client"
        }
        """

        let decoder = JSONDecoder()
        let data = json.data(using: .utf8)!
        let decoded = try decoder.decode(WebSocketMessageMetadata.self, from: data)

        #expect(decoded.timestamp == "2026-03-03T10:00:00Z")
        #expect(decoded.direction == "server_to_client")
        #expect(decoded.sessionId == nil)
        #expect(decoded.projectId == nil)
        #expect(decoded.messageId == nil)
    }

    // MARK: - Attachment

    @Test("Attachment dogru decode edilmeli")
    func attachmentDecode() throws {
        let json = """
        {
            "type": "image",
            "url": "https://s3.example.com/img.png",
            "mime_type": "image/png",
            "size_bytes": 1024
        }
        """

        let decoder = JSONDecoder()
        let data = json.data(using: .utf8)!
        let decoded = try decoder.decode(WebSocketMessageAttachment.self, from: data)

        #expect(decoded.type == "image")
        #expect(decoded.url == "https://s3.example.com/img.png")
        #expect(decoded.mimeType == "image/png")
        #expect(decoded.sizeBytes == 1024)
    }

    // MARK: - MessageType Enum

    @Test("WebSocketMessageType rawValue'lar dogru olmali")
    func messageTypeRawValues() {
        #expect(WebSocketMessageType.connectionAck.rawValue == "connection_ack")
        #expect(WebSocketMessageType.text.rawValue == "text")
        #expect(WebSocketMessageType.error.rawValue == "error")
        #expect(WebSocketMessageType.progress.rawValue == "progress")
        #expect(WebSocketMessageType.ping.rawValue == "ping")
        #expect(WebSocketMessageType.pong.rawValue == "pong")
    }

    // MARK: - MessageDirection Enum

    @Test("WebSocketMessageDirection rawValue'lar dogru olmali")
    func messageDirectionRawValues() {
        #expect(WebSocketMessageDirection.clientToServer.rawValue == "client_to_server")
        #expect(WebSocketMessageDirection.serverToClient.rawValue == "server_to_client")
    }

    // MARK: - Message Factory

    @Test("textMessage factory dogru mesaj olusturmali")
    func textMessageFactory() {
        let message = WebSocketMessageFactory.textMessage(
            "Test mesaji",
            sessionId: "sess-1",
            projectId: "proj-1"
        )

        #expect(message.type == "text")
        #expect(message.metadata?.sessionId == "sess-1")
        #expect(message.metadata?.projectId == "proj-1")
        #expect(message.metadata?.direction == "client_to_server")

        if case .text(let text) = message.content {
            #expect(text == "Test mesaji")
        } else {
            Issue.record("Content text olmali")
        }
    }

    @Test("pingMessage factory dogru mesaj olusturmali")
    func pingMessageFactory() {
        let message = WebSocketMessageFactory.pingMessage()

        #expect(message.type == "ping")
        #expect(!message.id.isEmpty)

        if case .heartbeat = message.content {
            // Basarili
        } else {
            Issue.record("Content heartbeat olmali")
        }
    }

    @Test("pongMessage factory dogru mesaj olusturmali")
    func pongMessageFactory() {
        let message = WebSocketMessageFactory.pongMessage()

        #expect(message.type == "pong")

        if case .heartbeat = message.content {
            // Basarili
        } else {
            Issue.record("Content heartbeat olmali")
        }
    }

    // MARK: - TaskStatus Content (T0.6 — Doc 10 §6.3.1)

    /// Backend Pydantic snake_case payload (`task_id`) iOS Swift camelCase (`taskId`)
    /// alanina dogru decode olmali. Eski `keyNotFound(taskId)` hatasi `CodingKeys`
    /// eklenmesi ile cozuldu. Default JSONDecoder (snake_case strategy yok) ile bile
    /// calismali — explicit CodingKeys garanti saglar.
    @Test("TaskStatusContent default JSONDecoder ile snake_case'den decode edilmeli")
    func taskStatusContentDecodeWithDefaultDecoder() throws {
        let json = #"""
        {"task_id": "abc-123", "status": "completed", "progress_pct": 100, "completed_steps": 4, "total_steps": 4}
        """#
        let data = try #require(json.data(using: .utf8))

        let decoder = JSONDecoder()
        let content = try decoder.decode(TaskStatusContent.self, from: data)

        #expect(content.taskId == "abc-123")
        #expect(content.status == "completed")
        #expect(content.progressPct == 100)
        #expect(content.completedSteps == 4)
        #expect(content.totalSteps == 4)
        #expect(content.currentStep == nil)
        #expect(content.detail == nil)
    }

    @Test("TaskStatusContent tum alanlarla snake_case'den decode edilmeli")
    func taskStatusContentDecodeFull() throws {
        let json = #"""
        {
            "task_id": "task-42",
            "status": "implementing",
            "current_step": "implementing",
            "progress_pct": 65,
            "completed_steps": 2,
            "total_steps": 4,
            "detail": "Refactoring complete"
        }
        """#
        let data = try #require(json.data(using: .utf8))

        let decoder = JSONDecoder()
        let content = try decoder.decode(TaskStatusContent.self, from: data)

        #expect(content.taskId == "task-42")
        #expect(content.status == "implementing")
        #expect(content.currentStep == "implementing")
        #expect(content.progressPct == 65)
        #expect(content.completedSteps == 2)
        #expect(content.totalSteps == 4)
        #expect(content.detail == "Refactoring complete")
    }

    @Test("task_status mesaji WebSocketBaseMessage uzerinden decode edilmeli (Router yolu)")
    func taskStatusMessageRouterDecode() throws {
        // Router'in kullandigi snake_case strategy ile end-to-end decode
        let json = #"""
        {
            "id": "ws-msg-1",
            "type": "task_status",
            "content": {
                "task_id": "task-abc",
                "status": "testing",
                "current_step": "testing",
                "progress_pct": 80,
                "completed_steps": 3,
                "total_steps": 4,
                "detail": "Tests running"
            }
        }
        """#
        let data = try #require(json.data(using: .utf8))

        let decoder = JSONDecoder()
        let message = try decoder.decode(WebSocketBaseMessage.self, from: data)

        #expect(message.type == "task_status")
        if case .taskStatus(let task) = message.content {
            #expect(task.taskId == "task-abc")
            #expect(task.status == "testing")
            #expect(task.currentStep == "testing")
            #expect(task.progressPct == 80)
            #expect(task.completedSteps == 3)
            #expect(task.totalSteps == 4)
            #expect(task.detail == "Tests running")
        } else {
            Issue.record("Content taskStatus olmali")
        }
    }

    // MARK: - V1.5 Question Content (backend QUESTION envelope)

    @Test("question envelope ApprovalQuestionDTO icine decode edilmeli")
    func questionEnvelopeDecode() throws {
        // Backend reference: apps/backend/app/services/approval_service.py::build_question_message
        // V1.4-fix HIGH: timeout_seconds bridge_timeout_seconds yansitir (clamped 30s).
        let json = """
        {
            "id": "msg-q-1",
            "type": "question",
            "content": {
                "approval_id": "appr-uuid-123",
                "question": "rm -rf /tmp/build.log",
                "context": "Tool: Bash, Action: rm -rf /tmp/build.log",
                "options": [
                    {"id": "approve", "label": "Onayla", "style": "primary"},
                    {"id": "reject", "label": "Reddet", "style": "danger"}
                ],
                "timeout_seconds": 30,
                "category": "destructive"
            },
            "metadata": {
                "timestamp": "2026-05-02T12:00:00Z",
                "session_id": "sess-789",
                "direction": "server_to_client"
            }
        }
        """
        let data = try #require(json.data(using: .utf8))
        let decoder = JSONDecoder()
        let message = try decoder.decode(WebSocketBaseMessage.self, from: data)

        #expect(message.type == "question")
        #expect(message.metadata?.sessionId == "sess-789")

        if case .question(let dto) = message.content {
            #expect(dto.approvalId == "appr-uuid-123")
            #expect(dto.question == "rm -rf /tmp/build.log")
            #expect(dto.context == "Tool: Bash, Action: rm -rf /tmp/build.log")
            #expect(dto.timeoutSeconds == 30)
            #expect(dto.category == "destructive")
            #expect(dto.options.count == 2)
            #expect(dto.options[0].id == "approve")
            #expect(dto.options[0].style == "primary")
            #expect(dto.options[1].id == "reject")
            #expect(dto.options[1].style == "danger")
        } else {
            Issue.record("Content question(ApprovalQuestionDTO) olmali")
        }
    }

    @Test("question MessageType enum 'question' raw value'ya sahip")
    func questionMessageTypeRawValue() {
        #expect(WebSocketMessageType.question.rawValue == "question")
    }
}
