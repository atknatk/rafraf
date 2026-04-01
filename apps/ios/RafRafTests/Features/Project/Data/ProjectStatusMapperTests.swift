import Testing
@testable import RafRaf

/// ProjectStatusMapper DTO -> Domain model donusum testleri.
struct ProjectStatusMapperTests {
    @Test("ProjectSummaryDTO domain modele dogru donusur")
    func summaryDTOToDomain() {
        let dto = ProjectSummaryDTO(
            id: "test-id",
            name: "Test Project",
            status: "active",
            localPath: nil,
            lastActivityAt: "2026-03-03T10:00:00Z",
            lastActivitySummary: "PR merged",
            techStack: ["Swift", "Python"]
        )

        let project = ProjectStatusMapper.toDomain(from: dto)

        #expect(project.id == "test-id")
        #expect(project.name == "Test Project")
        #expect(project.status == .active)
        #expect(project.techStack.count == 2)
        #expect(project.lastActivitySummary == "PR merged")
        #expect(project.lastActivityAt != nil)
    }

    @Test("ProjectDetailDTO domain modele dogru donusur")
    func detailDTOToDomain() {
        let dto = ProjectDetailDTO(
            id: "detail-id",
            name: "Detail Project",
            description: "A detailed project",
            status: "pending",
            repositoryUrl: "https://github.com/test/repo",
            localPath: nil,
            techStack: ["FastAPI"],
            lastActivityAt: nil,
            lastActivitySummary: nil,
            createdAt: "2026-03-03T10:00:00Z",
            updatedAt: "2026-03-03T10:00:00Z"
        )

        let project = ProjectStatusMapper.toDomain(from: dto)

        #expect(project.id == "detail-id")
        #expect(project.name == "Detail Project")
        #expect(project.description == "A detailed project")
        #expect(project.status == .pending)
        #expect(project.repositoryURL == "https://github.com/test/repo")
        #expect(project.lastActivityAt == nil)
    }

    @Test("ProjectListResponseDTO domain modele dogru donusur")
    func listResponseToDomain() {
        let dto = ProjectListResponseDTO(
            projects: [
                ProjectSummaryDTO(
                    id: "1",
                    name: "Project 1",
                    status: "active",
                    localPath: nil,
                    lastActivityAt: nil,
                    lastActivitySummary: nil,
                    techStack: []
                ),
                ProjectSummaryDTO(
                    id: "2",
                    name: "Project 2",
                    status: "completed",
                    localPath: nil,
                    lastActivityAt: nil,
                    lastActivitySummary: nil,
                    techStack: ["Node.js"]
                )
            ],
            total: 2,
            page: 1,
            pageSize: 20
        )

        let result = ProjectStatusMapper.toDomain(from: dto)

        #expect(result.projects.count == 2)
        #expect(result.total == 2)
        #expect(result.page == 1)
        #expect(result.pageSize == 20)
        #expect(result.hasMore == false)
    }

    @Test("Bilinmeyen status degeri active olarak default alinir")
    func unknownStatusDefaultsToActive() {
        let dto = ProjectSummaryDTO(
            id: "test",
            name: "Unknown",
            status: "unknown_status",
            localPath: nil,
            lastActivityAt: nil,
            lastActivitySummary: nil,
            techStack: []
        )

        let project = ProjectStatusMapper.toDomain(from: dto)

        #expect(project.status == .active)
    }

    @Test("hasMore sayfalama sonucunu dogru hesaplar")
    func hasMorePagination() {
        let fullPage = ProjectListResult(
            projects: [],
            total: 50,
            page: 1,
            pageSize: 20
        )
        #expect(fullPage.hasMore == true)

        let lastPage = ProjectListResult(
            projects: [],
            total: 40,
            page: 2,
            pageSize: 20
        )
        #expect(lastPage.hasMore == false)
    }
}
