# Feature: iOS Scaffold + Tab Nav + Design System (RF*)

**Issue**: #24
**Faz**: F4
**Katmanlar**: ios
**Pipeline**: full
**Tarih**: 2026-03-03

## Ozet

iOS uygulamasinin temel iskeletini olusturur. Tab navigation (Chat, Projects/Home, Settings), RF* design system base componentleri (RFButton, RFCard, RFTextField, RFLoadingView, RFEmptyStateView, RFErrorView), color/typography token sistemi, dark mode destegi, Clean Architecture katman yapisi ve DI container (Factory pattern) icerir. Bu feature, sonraki tum iOS feature'larinin uzerine insa edilecegi temel altyapidir.

## Degisecek Dosyalar

### iOS (`apps/ios/`)

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `RafRaf/App/ContentView.swift` | MODIFY | Tab navigation'a Projects tab eklenmesi |
| `RafRaf/DesignSystem/Components/RFButton.swift` | MODIFY | Destructive stil iyilestirmesi, dark mode uyumu |
| `RafRaf/DesignSystem/Components/RFCard.swift` | MODIFY | Interactive variant eklenmesi |
| `RafRaf/DesignSystem/Components/RFTextField.swift` | MODIFY | Multiline destek eklenmesi |
| `RafRaf/DesignSystem/Components/RFLoadingView.swift` | MODIFY | Animasyon iyilestirmesi |
| `RafRaf/DesignSystem/Components/RFEmptyStateView.swift` | MODIFY | Iyilestirmeler |
| `RafRaf/DesignSystem/Components/RFErrorView.swift` | CREATE | Hata goruntuleme bileseni |
| `RafRaf/DesignSystem/Theme/RFColors.swift` | MODIFY | Dark mode renkleri eklenmesi |
| `RafRaf/DesignSystem/Theme/RFTypography.swift` | MODIFY | Ek font stilleri |
| `RafRaf/DesignSystem/Theme/RFSpacing.swift` | MODIFY | Gerekirse ek spacing degerleri |
| `RafRaf/Core/DI/AppContainer.swift` | MODIFY | Yeni dependency'ler icin genisletme |
| `RafRaf/Features/Chat/Presentation/Views/ChatView.swift` | MODIFY | RF* component uyumu |
| `RafRaf/Features/Home/Presentation/Views/HomeView.swift` | MODIFY | RF* component uyumu |
| `RafRaf/Features/Settings/Presentation/Views/SettingsView.swift` | MODIFY | RF* component uyumu |

## API Endpoints

Bu feature herhangi bir backend API endpoint'i gerektirmez. Tamamen iOS client-side feature'dir.

### REST

Yok.

### WebSocket Messages

Yok.

## Data Model

### Swift Models

Mevcut modeller kullanilir. Yeni model eklenmesi gerekmez.

## Business Rules

1. Tab navigation 3 tab icermeli: Chat, Home (Projects), Settings
2. Tum RF* componentler dark mode desteklemeli
3. RFButton primary, secondary, destructive stiller desteklemeli
4. RFCard standard ve interactive varyantlari olmali
5. RFTextField text, secure ve multiline mod desteklemeli
6. RFErrorView retry butonu ve hata mesaji gostermeli
7. Her component icin `#Preview` olmali
8. Tum kullanici-gorunur stringler `String(localized:)` ile localized olmali
9. Feature ekranlarinda raw SwiftUI (Button, Text, TextField vb.) YASAK — sadece RF* componentler

## Test Requirements

### iOS
- [ ] Unit test: RFButton stiller ve durumlar
- [ ] Unit test: RFCard varyantlari
- [ ] Unit test: RFTextField validation ve modlar
- [ ] Unit test: RFErrorView retry callback
- [ ] Unit test: ContentView tab navigation
- [ ] Unit test: ViewModel basit testleri (ChatViewModel, HomeViewModel, SettingsViewModel)

## Acceptance Criteria

- [ ] Tab navigation (Chat, Home/Projects, Settings) calisir
- [ ] RFButton primary, secondary, destructive stilleri dogru render edilir
- [ ] RFCard standard ve interactive varyantlari calisir
- [ ] RFTextField text, secure ve multiline modlari calisir
- [ ] RFLoadingView dogru gorunur
- [ ] RFEmptyStateView dogru gorunur
- [ ] RFErrorView olusturuldu ve dogru gorunur
- [ ] Color/typography token sistemi mevcut
- [ ] Dark mode destegi tum componentlerde calisir
- [ ] Clean Architecture katman yapisi korunuyor
- [ ] DI container (Factory pattern) yapilandirild
- [ ] Her component icin #Preview mevcut
- [ ] Tum stringler String(localized:) ile localized
