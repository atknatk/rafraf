import Foundation
import Testing
@testable import RafRaf

/// ProjectMapper testleri.
@Suite("ProjectMapper Tests")
struct ProjectMapperTests {

    @Test("toDomain tek DTO'yu dogru domain modeline donusturmeli")
    func toDomainSingle() {
        let dto = ProjectDTO(
            id: "proj-1",
            name: "Test Proje",
            description: "Test aciklamasi",
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-02T00:00:00Z",
            status: "active"
        )

        let project = ProjectMapper.toDomain(dto)

        #expect(project.id == "proj-1")
        #expect(project.name == "Test Proje")
        #expect(project.description == "Test aciklamasi")
        #expect(project.status == .active)
    }

    @Test("toDomain gecersiz status durumunda active donmeli")
    func toDomainInvalidStatus() {
        let dto = ProjectDTO(
            id: "proj-2",
            name: "Proje",
            description: "Aciklama",
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-02T00:00:00Z",
            status: "invalid_status"
        )

        let project = ProjectMapper.toDomain(dto)

        #expect(project.status == .active)
    }

    @Test("toDomain liste donusumu dogru calistirilmali")
    func toDomainList() {
        let dtos = [
            ProjectDTO(
                id: "1", name: "A", description: "a",
                createdAt: "2026-01-01T00:00:00Z",
                updatedAt: "2026-01-02T00:00:00Z",
                status: "active"
            ),
            ProjectDTO(
                id: "2", name: "B", description: "b",
                createdAt: "2026-01-01T00:00:00Z",
                updatedAt: "2026-01-02T00:00:00Z",
                status: "archived"
            ),
        ]

        let projects = ProjectMapper.toDomain(dtos)

        #expect(projects.count == 2)
        #expect(projects[0].id == "1")
        #expect(projects[1].status == .archived)
    }

    @Test("toDomain gecersiz tarih durumunda fallback Date kullanmali")
    func toDomainInvalidDate() {
        let dto = ProjectDTO(
            id: "proj-3",
            name: "Proje",
            description: "Aciklama",
            createdAt: "gecersiz-tarih",
            updatedAt: "gecersiz-tarih",
            status: "completed"
        )

        let project = ProjectMapper.toDomain(dto)

        // Gecersiz tarihte fallback Date() kullanilir, crash olmamali
        #expect(project.status == .completed)
    }
}
