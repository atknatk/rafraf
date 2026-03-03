# Developer Handoff: Screenshot Viewer (Pinch-to-Zoom)

**Issue**: #31
**Branch**: feature/f5/31-f5-02-screenshot-viewer-pinch-to-zoom
**Tarih**: 2026-03-03
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/ios/RafRaf/Features/ScreenshotViewer/Domain/Models/Screenshot.swift` | CREATE | Screenshot domain modeli |
| `apps/ios/RafRaf/Features/ScreenshotViewer/Domain/Models/ScreenshotViewerState.swift` | CREATE | Viewer durum enum'i |
| `apps/ios/RafRaf/Features/ScreenshotViewer/Domain/Repositories/ScreenshotRepositoryProtocol.swift` | CREATE | Repository protokolu |
| `apps/ios/RafRaf/Features/ScreenshotViewer/Domain/UseCases/LoadScreenshotUseCase.swift` | CREATE | Screenshot yukleme use case |
| `apps/ios/RafRaf/Features/ScreenshotViewer/Data/DTOs/ScreenshotDTO.swift` | CREATE | API response DTO |
| `apps/ios/RafRaf/Features/ScreenshotViewer/Data/Mappers/ScreenshotMapper.swift` | CREATE | DTO -> Domain mapper |
| `apps/ios/RafRaf/Features/ScreenshotViewer/Data/Repositories/ScreenshotRepositoryImpl.swift` | CREATE | Repository implementasyonu |
| `apps/ios/RafRaf/Features/ScreenshotViewer/Presentation/ViewModels/ScreenshotViewerViewModel.swift` | CREATE | ViewModel - zoom/pan state yonetimi |
| `apps/ios/RafRaf/Features/ScreenshotViewer/Presentation/Components/RFScreenshotViewer.swift` | CREATE | Inline screenshot goruntuleyici bilesen |
| `apps/ios/RafRaf/Features/ScreenshotViewer/Presentation/Components/RFScreenshotFullScreenView.swift` | CREATE | Tam ekran goruntuleyici modal |
| `apps/ios/RafRaf/Features/ScreenshotViewer/Presentation/Views/ScreenshotViewerView.swift` | CREATE | Ana ekran - inline + full-screen entegrasyonu |
| `apps/ios/RafRaf/Core/DI/AppContainer.swift` | MODIFY | Screenshot viewer DI kayitlari eklendi |

## Ozellikler

- RFScreenshotViewer: Inline gorsel goruntuleyici, Nuke ile async loading
- Pinch-to-zoom: MagnifyGesture ile 1x-5x zoom araligi
- Pan gesture: DragGesture ile zoom durumunda gorsel kaydirma
- Double-tap zoom: Cift tikla 2.5x zoom, tekrar tikla reset
- Full-screen modal: fullScreenCover ile tam ekran goruntuleyici
- Loading state: ProgressView ile yukleme gostergesi
- Error state: RFErrorView ile hata gosterimi ve retry
- Nuke (LazyImage) ile yuksek performansli async image loading
- RF* design system bilesenleri kullanildi (RFCard, RFText, RFButton, RFLoadingView, RFErrorView)
- Tum stringler localized: String(localized:)
- Her view dosyasinda #Preview blogu mevcut

## API Kontrat Uyumu

Bu feature sadece iOS katmanini icermektedir. Screenshot'lar chat attachment'lari uzerinden gelir (ChatAttachment.type == .image). API kontrat uyumu mevcut Chat kontratina dayanir.

## Notlar

- Zoom scale ve offset animasyonlari interactiveSpring ile yapilmistir
- Minimum zoom 1x, maksimum zoom 5x olarak sinirlandirilmistir
- Pan yalnizca zoom > 1 iken aktif olur
- Zoom reset oldugunda offset da sifirlanir
- Clean Architecture katman izolasyonu saglanmistir: Domain -> Data -> Presentation
- Factory DI ile tum bagimliliklar kayit edilmistir
