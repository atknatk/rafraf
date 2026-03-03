# Feature: Project Status Cards

**Issue**: #32
**Faz**: F5
**Katmanlar**: backend, ios
**Pipeline**: full
**Tarih**: 2026-03-03

## Ozet

Proje durumunu gosteren kart componentleri. Kullanici, projelerini liste gorunumunde gorebilir, detay ekranina gecebilir ve her projenin durumunu (aktif, beklemede, tamamlandi) goruntuleyebilir. Son aktivite ozeti ve pull-to-refresh destegi saglanir.

## Degisecek Dosyalar

### Backend (`apps/backend/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/models/project.py` | CREATE | Project SQLAlchemy modeli |
| `app/schemas/projects.py` | CREATE | Pydantic request/response schemalar |
| `app/repositories/project_repo.py` | CREATE | Proje DB erisim katmani |
| `app/services/project_service.py` | CREATE | Proje business logic |
| `app/api/routes/projects.py` | CREATE | REST endpoint'ler |
| `app/main.py` | MODIFY | projects router ekleme |

### iOS (`apps/ios/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `RafRaf/Features/Project/Data/DTOs/ProjectDTO.swift` | CREATE | Proje API response DTO |
| `RafRaf/Features/Project/Data/Mappers/ProjectMapper.swift` | CREATE | DTO -> Domain donusumu |
| `RafRaf/Features/Project/Data/Repositories/ProjectRepositoryImpl.swift` | CREATE | Repository implementasyonu |
| `RafRaf/Features/Project/Domain/Models/Project.swift` | CREATE | Proje domain modeli |
| `RafRaf/Features/Project/Domain/Repositories/ProjectRepositoryProtocol.swift` | CREATE | Repository protokolu |
| `RafRaf/Features/Project/Domain/UseCases/GetProjectsUseCase.swift` | CREATE | Proje listesi use case |
| `RafRaf/Features/Project/Domain/UseCases/GetProjectDetailUseCase.swift` | CREATE | Proje detay use case |
| `RafRaf/Features/Project/Presentation/Views/ProjectListView.swift` | CREATE | Proje listesi ekrani |
| `RafRaf/Features/Project/Presentation/Views/ProjectDetailView.swift` | CREATE | Proje detay ekrani |
| `RafRaf/Features/Project/Presentation/ViewModels/ProjectListViewModel.swift` | CREATE | Liste ViewModel |
| `RafRaf/Features/Project/Presentation/ViewModels/ProjectDetailViewModel.swift` | CREATE | Detay ViewModel |
| `RafRaf/Features/Project/Presentation/Components/RFProjectCard.swift` | CREATE | Proje kart componenti |
| `RafRaf/Features/Project/Presentation/Components/RFProjectStatusBadge.swift` | CREATE | Durum gostergesi |

## API Endpoints

### REST
| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| GET | `/api/v1/projects` | query: `status`, `page`, `page_size` | `ProjectListResponse` | Proje listesi |
| GET | `/api/v1/projects/{project_id}` | - | `ProjectDetailResponse` | Proje detayi |

## Data Model

### PostgreSQL
```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    repository_url VARCHAR(512),
    tech_stack TEXT[] DEFAULT '{}',
    last_activity_at TIMESTAMPTZ,
    last_activity_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_projects_status ON projects(status);
```

### Pydantic Models
```python
class ProjectStatus(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"
    COMPLETED = "completed"

class ProjectModel(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: uuid.UUID
    name: str
    description: str | None
    status: ProjectStatus
    repository_url: str | None
    tech_stack: list[str]
    last_activity_at: datetime | None
    last_activity_summary: str | None
    created_at: datetime
    updated_at: datetime
```

### Swift Models
```swift
struct Project: Identifiable, Sendable, Equatable {
    let id: String
    let name: String
    let description: String?
    let status: ProjectStatus
    let repositoryURL: String?
    let techStack: [String]
    let lastActivityAt: Date?
    let lastActivitySummary: String?
    let createdAt: Date
    let updatedAt: Date
}

enum ProjectStatus: String, Sendable, Equatable, CaseIterable {
    case active
    case pending
    case completed
}
```

## Business Rules

1. Proje listesi varsayilan olarak tum projerleri gosterir, status parametresi ile filtrelenebilir
2. Proje durumu sadece `active`, `pending`, `completed` olabilir
3. Son aktivite ozeti son guncelleme zamanini ve kisa aciklamayi icerir
4. Pull-to-refresh ile liste yeniden yuklenir
5. Sayfalama: varsayilan `page_size=20`, maksimum `page_size=100`

## Test Requirements

### Backend
- [ ] Unit test: ProjectService.get_projects - filtreleme + sayfalama
- [ ] Unit test: ProjectService.get_project_by_id - bulunan + bulunamayan
- [ ] Integration test: GET /api/v1/projects - response format dogrulama
- [ ] Integration test: GET /api/v1/projects/{id} - 200 + 404 senaryolari

### iOS
- [ ] Unit test: ProjectListViewModel - yukleme, hata, yenileme
- [ ] Unit test: ProjectDetailViewModel - yukleme, hata
- [ ] Unit test: GetProjectsUseCase - basarili + hata
- [ ] Unit test: ProjectMapper - DTO donusumu
- [ ] UI test: Pull-to-refresh davranisi

## Acceptance Criteria

- [ ] RFProjectCard componenti olusturuldu ve RF* standartlarina uygun
- [ ] Proje listesi ekrani (ProjectListView) calisir durumda
- [ ] Proje detay ekrani (ProjectDetailView) calisir durumda
- [ ] Durum gostergesi (aktif, beklemede, tamamlandi) gorsel olarak farkli
- [ ] Son aktivite ozeti gosterilir
- [ ] Pull-to-refresh calisir
- [ ] #Preview tum view'larda mevcut
- [ ] Unit testler yazildi
- [ ] Coverage >= 70% (iOS)
