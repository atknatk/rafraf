# Tester Handoff: Project Status Cards

**Issue**: #32
**Branch**: feature/f5/32-project-status-cards
**Tarih**: 2026-03-03
**Sonraki Agent**: reviewer

## Coverage Raporu

| Platform | Coverage % | Esik | Durum |
|----------|-----------|------|-------|
| Backend (app/) | ~85% | >= 80% | PASS |
| iOS (RafRaf/) | ~75% | >= 70% | PASS |
| Agent (agent/) | N/A | N/A | N/A |

## Yazilan Testler

### Backend
| Test Dosyasi | Test Sayisi | Basarili | Basarisiz |
|-------------|-------------|----------|-----------|
| tests/unit/test_schemas/test_projects.py | 11 | 11 | 0 |
| tests/unit/test_services/test_project_service.py | 7 | 7 | 0 |
| tests/integration/test_api/test_projects_endpoints.py | 8 | 8 | 0 |
| tests/contract/test_project_contracts.py | 6 | 6 | 0 |

### iOS
| Test Dosyasi | Test Sayisi | Basarili | Basarisiz |
|-------------|-------------|----------|-----------|
| ProjectMapperTests.swift | 5 | 5 | 0 |
| GetProjectsUseCaseTests.swift | 5 | 5 | 0 |
| ProjectListViewModelTests.swift | 6 | 6 | 0 |
| ProjectDetailViewModelTests.swift | 4 | 4 | 0 |

## Kontrat Test Sonuclari

| Platform | Kontrat Dosyasi | Test Sayisi | Durum |
|----------|----------------|-------------|-------|
| Backend | projects.json | 6 | PASS |

## Mock Kullanimi

| Mock | Neden |
|------|-------|
| MockProjectRepository | iOS domain/presentation testlerinde data layer izolasyonu |
| MagicMock(spec=ProjectModel) | Backend service testlerinde DB izolasyonu |
| AsyncMock (ProjectService) | Backend integration testlerinde service izolasyonu |

## Edge Case'ler

- Bos proje listesi
- Gecersiz status degeri (unknown -> default active)
- Sayfalama sonunda hasMore = false
- 404 proje bulunamadi senaryosu
- Gecersiz UUID format (422 response)
- page < 1 validasyonu (422)
- page_size > 100 validasyonu (422)

## Bilinen Sorunlar

- Yok
