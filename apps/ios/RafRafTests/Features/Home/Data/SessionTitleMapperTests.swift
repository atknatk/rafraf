import Foundation
import Testing
@testable import RafRaf

/// `SessionTitleMapper` testleri.
@Suite("SessionTitleMapper Tests")
struct SessionTitleMapperTests {

    @Test("DTO domain modeline donusturulmeli — alanlar korunur")
    func mapsAllFields() {
        let date = Date(timeIntervalSince1970: 1_714_500_000)
        let content = SessionTitleContent(
            sessionId: UUID(uuidString: "00000000-0000-0000-0000-000000000123")!,
            aiTitle: "Backend test sonuclarinin incelenmesi",
            generatedAt: date
        )

        let domain = SessionTitleMapper.toDomain(content)

        #expect(domain.sessionId == "00000000-0000-0000-0000-000000000123")
        #expect(domain.aiTitle == "Backend test sonuclarinin incelenmesi")
        #expect(domain.generatedAt == date)
    }

    @Test("Identifiable id alani sessionId ile esit olmali — UUID lowercased canonical")
    func identifiableMatchesSessionId() {
        let uuid = UUID()
        let content = SessionTitleContent(
            sessionId: uuid,
            aiTitle: "x",
            generatedAt: Date()
        )

        let domain = SessionTitleMapper.toDomain(content)

        #expect(domain.id == uuid.uuidString.lowercased())
    }

    @Test("Bos aiTitle korunur — domain validation katmaninda kontrol edilir")
    func emptyTitlePreserved() {
        let content = SessionTitleContent(
            sessionId: UUID(),
            aiTitle: "",
            generatedAt: Date()
        )

        let domain = SessionTitleMapper.toDomain(content)

        #expect(domain.aiTitle.isEmpty)
    }
}
