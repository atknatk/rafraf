# Developer Handoff: iOS Scaffold + Tab Nav + Design System (RF*)

**Issue**: #24
**Branch**: feature/f4/24-f4-01-ios-scaffold-tab-nav-design
**Tarih**: 2026-03-03
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/ios/RafRaf/DesignSystem/Components/RFErrorView.swift` | CREATE | Hata goruntuleme bileseni - retry destegi ile |
| `apps/ios/RafRaf/DesignSystem/Components/RFCard.swift` | MODIFY | Interactive stil eklendi (RFCardStyle enum, onTap callback) |
| `apps/ios/RafRaf/DesignSystem/Components/RFTextField.swift` | MODIFY | Multiline mod eklendi (RFTextFieldMode enum, axis: .vertical) |
| `apps/ios/RafRaf/DesignSystem/Theme/RFColors.swift` | MODIFY | Dark mode destegi eklendi (Color light/dark extension, chat bubble renkleri) |

## Mevcut Yapi (Onceden Olusturulmus)

Asagidaki dosyalar F0-05 (iOS project scaffold) issue'sunda zaten olusturulmustur ve bu feature'da korunmustur:

- Tab navigation (ContentView.swift) - Chat, Home, Settings
- RFButton (primary, secondary, outline, ghost, destructive)
- RFText, RFAvatar, RFLoadingView, RFEmptyStateView
- RFTypography, RFSpacing
- Clean Architecture katman yapisi (Data/Domain/Presentation)
- DI container (Factory pattern - AppContainer.swift)
- ChatView, HomeView, SettingsView
- ChatViewModel, HomeViewModel, SettingsViewModel
- Domain modeller (ChatMessage, Project, UserProfile)

## Yeni/Degistirilmis Componentler

### RFErrorView (Yeni)
- Hata ikonu, baslik, mesaj gosterir
- Opsiyonel retry butonu (RFButton primary kullanir)
- `#Preview` mevcut

### RFCard - Interactive Stil (Guncellenmis)
- `RFCardStyle` enum: `.standard`, `.interactive`
- `.interactive` stil `onTap` callback ile tiklanabilir kart saglar
- `ButtonStyle(.plain)` ile native SwiftUI buton davranisi
- Geriye donuk uyumlu (default `.standard`)

### RFTextField - Multiline Mod (Guncellenmis)
- `RFTextFieldMode` enum: `.text`, `.secure`, `.multiline`
- `.multiline` mod `TextField(axis: .vertical)` ile cok satirli giris
- `lineLimit` parametresi (varsayilan 3...6)
- Geriye donuk uyumlu `isSecure` init mevcut

### RFColors - Dark Mode (Guncellenmis)
- `Color(light:dark:)` extension ile dark mode renk destegi
- `fallbackPrimary`: Light'ta koyu mavi (#1B2A4A), dark'ta acik mavi (#5B9BD5)
- Chat bubble renkleri: `aiBubble`, `userBubble`
- `fallbackTextTertiary`, `divider` eklendi
- Tum fallback renkler UIKit dynamic color sistemi kullanir

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| swiftlint | N/A | SwiftLint konfigurasyonu mevcut degil (scaffold asamasinda) |
| xcodebuild build | N/A | xcodeproj mevcut degil, SPM Package.swift kullaniliyor |
| xcodebuild test | N/A | xcodeproj mevcut degil |

## API Kontrat Uyumu

Bu feature herhangi bir API endpoint icermez. Kontrat dogrulamasi gerekli degil.

## Notlar

- iOS projesi SPM (Package.swift) ile yonetiliyor, xcodeproj mevcut degil
- Tum yeni componentler `#Preview` iceriyor
- Geriye donuk uyumluluk saglanmis (mevcut RFCard ve RFTextField kullanimi bozulmaz)
- Dark mode destegi `Color(light:dark:)` extension ile saglanmis (UIKit UIColor dynamic system kullanir)
- Feature ekranlarinda (ChatView, HomeView, SettingsView) raw SwiftUI kullanilmiyor, tamamen RF* componentler kullaniliyor
- Tum kullanici-gorunur stringler `String(localized:)` ile localized
