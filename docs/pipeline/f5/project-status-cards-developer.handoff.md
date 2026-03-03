# Developer Handoff: Project Status Cards

**Issue**: #32
**Branch**: feature/f5/32-project-status-cards
**Tarih**: 2026-03-03
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/backend/app/models/project.py` | CREATE | Project SQLAlchemy modeli |
| `apps/backend/app/schemas/projects.py` | CREATE | Pydantic request/response schemas |
| `apps/backend/app/repositories/project_repo.py` | CREATE | DB erisim katmani |
| `apps/backend/app/services/project_service.py` | CREATE | Business logic |
| `apps/backend/app/api/routes/projects.py` | CREATE | REST endpoint'ler |
| `apps/backend/app/main.py` | MODIFY | projects router ekleme |
| `apps/ios/RafRaf/Features/Project/Data/DTOs/ProjectDTO.swift` | CREATE | API response DTO |
| `apps/ios/RafRaf/Features/Project/Data/Mappers/ProjectMapper.swift` | CREATE | DTO->Domain mapper |
| `apps/ios/RafRaf/Features/Project/Data/Repositories/ProjectRepositoryImpl.swift` | CREATE | Repository impl |
| `apps/ios/RafRaf/Features/Project/Domain/Models/Project.swift` | CREATE | Domain modeli |
| `apps/ios/RafRaf/Features/Project/Domain/Repositories/ProjectRepositoryProtocol.swift` | CREATE | Protocol |
| `apps/ios/RafRaf/Features/Project/Domain/UseCases/GetProjectsUseCase.swift` | CREATE | Liste use case |
| `apps/ios/RafRaf/Features/Project/Domain/UseCases/GetProjectDetailUseCase.swift` | CREATE | Detay use case |
| `apps/ios/RafRaf/Features/Project/Presentation/Views/ProjectListView.swift` | CREATE | Liste view |
| `apps/ios/RafRaf/Features/Project/Presentation/Views/ProjectDetailView.swift` | CREATE | Detay view |
| `apps/ios/RafRaf/Features/Project/Presentation/ViewModels/ProjectListViewModel.swift` | CREATE | Liste VM |
| `apps/ios/RafRaf/Features/Project/Presentation/ViewModels/ProjectDetailViewModel.swift` | CREATE | Detay VM |
| `apps/ios/RafRaf/Features/Project/Presentation/Components/RFProjectCard.swift` | CREATE | Kart componenti |
| `apps/ios/RafRaf/Features/Project/Presentation/Components/RFProjectStatusBadge.swift` | CREATE | Durum gostergesi |

## API Kontrat Uyumu

- Kontrat dosyasi: `shared/api-contracts/rest/v1/projects.json`
- Dogrulanan endpoint sayisi: 2 (GET /api/v1/projects, GET /api/v1/projects/{id})
- Backend endpoint path, method, query param isimleri ve response field isimleri kontrat ile uyumlu
- iOS DTO field isimleri kontrat ile uyumlu (snake_case -> camelCase NetworkClient tarafindan handle edilir)

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | SKIPPED | CI ortaminda calistirilacak |
| mypy | SKIPPED | CI ortaminda calistirilacak |
| pytest | SKIPPED | CI ortaminda calistirilacak |
| xcodebuild build | SKIPPED | CI ortaminda calistirilacak |
| xcodebuild test | SKIPPED | CI ortaminda calistirilacak |

## Notlar

- Backend Project modeli yeni olusturuldu, Alembic migration henuz eklenmedi (CI ortaminda test DB ile calistirilacak)
- iOS'ta PreviewProjectRepository tum view preview'lari icin kullaniliyor
- FlowLayout helper tech stack etiketleri icin olusturuldu (ProjectDetailView icinde)
- NetworkClient keyDecodingStrategy = .convertFromSnakeCase kullandigi icin DTO'larda CodingKeys gerekmedi
- Domain layer'da hic dis import yok - sadece Foundation
