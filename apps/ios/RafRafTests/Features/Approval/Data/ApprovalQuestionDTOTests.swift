import Foundation
import Testing
@testable import RafRaf

/// ApprovalQuestionDTO decode testleri.
@Suite("ApprovalQuestionDTO Tests")
struct ApprovalQuestionDTOTests {

    // MARK: - JSON Decoding

    @Test("JSON'dan basarili decode edilmeli")
    func decodeFromJSON() throws {
        let json = """
        {
            "approval_id": "abc-123",
            "question": "Deploy onaylansin mi?",
            "context": "Image: rafraf:v1.0.0",
            "options": [
                {"id": "approve", "label": "Onayla", "style": "primary"},
                {"id": "reject", "label": "Reddet", "style": "danger"}
            ],
            "timeout_seconds": 30,
            "category": "deploy"
        }
        """

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = Data(json.utf8)
        let dto = try decoder.decode(ApprovalQuestionDTO.self, from: data)

        #expect(dto.approvalId == "abc-123")
        #expect(dto.question == "Deploy onaylansin mi?")
        #expect(dto.context == "Image: rafraf:v1.0.0")
        #expect(dto.options.count == 2)
        #expect(dto.timeoutSeconds == 30)
        #expect(dto.category == "deploy")
    }

    @Test("context null oldugunda basarili decode edilmeli")
    func decodeWithNullContext() throws {
        let json = """
        {
            "approval_id": "abc-123",
            "question": "Dosyalari sil?",
            "context": null,
            "options": [
                {"id": "approve", "label": "Sil", "style": "danger"},
                {"id": "reject", "label": "Iptal", "style": "secondary"}
            ],
            "timeout_seconds": 15,
            "category": "destructive"
        }
        """

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = Data(json.utf8)
        let dto = try decoder.decode(ApprovalQuestionDTO.self, from: data)

        #expect(dto.context == nil)
        #expect(dto.category == "destructive")
    }

    @Test("context alani eksik oldugunda basarili decode edilmeli")
    func decodeWithMissingContext() throws {
        let json = """
        {
            "approval_id": "abc-123",
            "question": "Dosyalari sil?",
            "options": [
                {"id": "approve", "label": "Sil", "style": "danger"}
            ],
            "timeout_seconds": 15,
            "category": "destructive"
        }
        """

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = Data(json.utf8)

        // context optional oldugundan eksik olabilir
        let dto = try decoder.decode(ApprovalQuestionDTO.self, from: data)
        #expect(dto.context == nil)
    }

    @Test("Birden fazla secenek ile decode edilmeli")
    func decodeMultipleOptions() throws {
        let json = """
        {
            "approval_id": "multi-123",
            "question": "Migration calistirilsin mi?",
            "context": null,
            "options": [
                {"id": "approve", "label": "Onayla", "style": "primary"},
                {"id": "detail", "label": "Detay", "style": "secondary"},
                {"id": "reject", "label": "Reddet", "style": "danger"}
            ],
            "timeout_seconds": 60,
            "category": "infrastructure"
        }
        """

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = Data(json.utf8)
        let dto = try decoder.decode(ApprovalQuestionDTO.self, from: data)

        #expect(dto.options.count == 3)
        #expect(dto.options[0].id == "approve")
        #expect(dto.options[1].id == "detail")
        #expect(dto.options[2].id == "reject")
    }
}

/// ApprovalResponseDTO encode testleri.
@Suite("ApprovalResponseDTO Tests")
struct ApprovalResponseDTOTests {

    @Test("JSON'a basarili encode edilmeli")
    func encodeToJSON() throws {
        let dto = ApprovalResponseDTO(
            approvalId: "abc-123",
            decision: "approved",
            note: nil
        )

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(dto)
        let json = try JSONDecoder().decode([String: String?].self, from: data)

        #expect(json["approval_id"] == "abc-123")
        #expect(json["decision"] == "approved")
    }

    @Test("Note ile encode edilmeli")
    func encodeWithNote() throws {
        let dto = ApprovalResponseDTO(
            approvalId: "abc-123",
            decision: "rejected",
            note: "Timeout - otomatik red"
        )

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(dto)
        let jsonString = String(data: data, encoding: .utf8)

        #expect(jsonString?.contains("rejected") == true)
        #expect(jsonString?.contains("Timeout") == true)
    }

    @Test("Roundtrip encode-decode basarili olmali")
    func roundtrip() throws {
        let original = ApprovalResponseDTO(
            approvalId: "roundtrip-123",
            decision: "approved",
            note: "Test notu"
        )

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(original)

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let decoded = try decoder.decode(ApprovalResponseDTO.self, from: data)

        #expect(decoded.approvalId == original.approvalId)
        #expect(decoded.decision == original.decision)
        #expect(decoded.note == original.note)
    }
}
