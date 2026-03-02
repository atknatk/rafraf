import Foundation
import Testing
@testable import RafRaf

/// RafRaf temel testleri.
/// Scaffold dogrulamasi icin basit smoke testler.
@Suite("RafRaf Scaffold Tests")
struct RafRafTests {

    @Test("Proje domain modeli olusturulabilmeli")
    func projectModelCreation() {
        let project = Project(
            id: "test-1",
            name: "Test Proje",
            description: "Test aciklama",
            createdAt: Date(),
            updatedAt: Date(),
            status: .active
        )

        #expect(project.id == "test-1")
        #expect(project.name == "Test Proje")
        #expect(project.status == ProjectStatus.active)
    }

    @Test("Chat mesaji domain modeli olusturulabilmeli")
    func chatMessageModelCreation() {
        let message = ChatMessage(
            id: "msg-1",
            content: "Merhaba",
            sender: MessageSender.user,
            timestamp: Date(),
            type: MessageType.text
        )

        #expect(message.id == "msg-1")
        #expect(message.content == "Merhaba")
        #expect(message.sender == MessageSender.user)
        #expect(message.type == MessageType.text)
    }

    @Test("Kullanici profil domain modeli olusturulabilmeli")
    func userProfileModelCreation() {
        let profile = UserProfile(
            id: "user-1",
            displayName: "Test User",
            email: "test@rafraf.app",
            avatarURL: nil,
            createdAt: Date()
        )

        #expect(profile.id == "user-1")
        #expect(profile.displayName == "Test User")
        #expect(profile.avatarURL == nil)
    }

    @Test("Proje mapper DTO'yu domain'e donusturebilmeli")
    func projectMapperConversion() {
        let dto = ProjectDTO(
            id: "test-1",
            name: "Test Proje",
            description: "Aciklama",
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-02T00:00:00Z",
            status: "active"
        )

        let project = ProjectMapper.toDomain(dto)

        #expect(project.id == "test-1")
        #expect(project.name == "Test Proje")
        #expect(project.status == ProjectStatus.active)
    }

    @Test("AppEnvironment development ortamini dondurmeli")
    func appEnvironmentDevelopment() {
        let env = AppEnvironment.current
        // DEBUG modda development olmali
        #expect(env == AppEnvironment.development)
    }
}
