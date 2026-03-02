# Developer Handoff: iOS project scaffold (Xcode + Clean Architecture skeleton)

**Issue**: #5
**Branch**: feature/f0/5-ios-project-scaffold-xcode-clean-arch
**Tarih**: 2026-03-02
**Sonraki Agent**: NONE (quick pipeline)

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/ios/Package.swift` | CREATE | SPM proje dosyasi - Factory ve Nuke bagimliliklari |
| `apps/ios/.swiftlint.yml` | CREATE | SwiftLint konfigurasyonu |
| `apps/ios/RafRaf/App/RafRafApp.swift` | CREATE | Uygulama giris noktasi (@main) |
| `apps/ios/RafRaf/App/ContentView.swift` | CREATE | Tab navigation yapisi (Home, Chat, Settings) |
| `apps/ios/RafRaf/App/AppEnvironment.swift` | CREATE | Ortam konfigurasyonu (dev/staging/prod URL'ler) |
| `apps/ios/RafRaf/Core/Networking/NetworkClient.swift` | CREATE | REST API istemcisi (URLSession) |
| `apps/ios/RafRaf/Core/Networking/WebSocketClient.swift` | CREATE | WebSocket istemcisi (native URLSession) |
| `apps/ios/RafRaf/Core/DI/AppContainer.swift` | CREATE | Factory DI container |
| `apps/ios/RafRaf/Core/Extensions/View+Extensions.swift` | CREATE | SwiftUI View uzantilari |
| `apps/ios/RafRaf/Core/Logging/AppLogger.swift` | CREATE | os.Logger wrapper |
| `apps/ios/RafRaf/DesignSystem/Theme/RFColors.swift` | CREATE | Renk paleti |
| `apps/ios/RafRaf/DesignSystem/Theme/RFTypography.swift` | CREATE | Tipografi sistemi |
| `apps/ios/RafRaf/DesignSystem/Theme/RFSpacing.swift` | CREATE | Bosluk sabitleri |
| `apps/ios/RafRaf/DesignSystem/Components/RFButton.swift` | CREATE | Buton bileseni |
| `apps/ios/RafRaf/DesignSystem/Components/RFText.swift` | CREATE | Metin bileseni |
| `apps/ios/RafRaf/DesignSystem/Components/RFCard.swift` | CREATE | Kart bileseni |
| `apps/ios/RafRaf/DesignSystem/Components/RFTextField.swift` | CREATE | Metin girisi bileseni |
| `apps/ios/RafRaf/DesignSystem/Components/RFLoadingView.swift` | CREATE | Yukleme gostergesi |
| `apps/ios/RafRaf/DesignSystem/Components/RFEmptyStateView.swift` | CREATE | Bos durum bileseni |
| `apps/ios/RafRaf/DesignSystem/Components/RFAvatar.swift` | CREATE | Avatar bileseni (Nuke entegrasyonu) |
| `apps/ios/RafRaf/Features/Home/` | CREATE | Home feature (Data/Domain/Presentation katmanlari) |
| `apps/ios/RafRaf/Features/Chat/` | CREATE | Chat feature (Data/Domain/Presentation katmanlari) |
| `apps/ios/RafRaf/Features/Settings/` | CREATE | Settings feature (Data/Domain/Presentation katmanlari) |
| `apps/ios/RafRaf/Resources/Localizable.xcstrings` | CREATE | Lokalizasyon dosyasi (TR + EN) |
| `apps/ios/RafRafTests/RafRafTests.swift` | CREATE | Temel smoke testler |

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| swiftlint | SKIP | CI ortaminda calistirilacak |
| xcodebuild build | SKIP | CI ortaminda calistirilacak (Xcode 16+ gerekli) |
| xcodebuild test | SKIP | CI ortaminda calistirilacak |
| Dosya yapisi dogrulama | PASS | Tum Clean Architecture katmanlari mevcut |

## Mimari Kararlar

- **SPM (Swift Package Manager)** tercih edildi, xcodeproj yerine Package.swift kullanildi
- **3 feature scaffold**: Home, Chat, Settings - her biri Clean Architecture (Data/Domain/Presentation) ile
- **RF* Design System**: RFButton, RFText, RFCard, RFTextField, RFLoadingView, RFEmptyStateView, RFAvatar
- **Factory DI**: Container extension pattern ile singleton kayitlar
- **Native WebSocket**: URLSession WebSocket API kullanildi (3rd party yok)
- **Nuke**: Async image loading icin NukeUI ile LazyImage entegrasyonu (RFAvatar'da)
- **os.Logger**: Structured logging, subsystem: "com.rafraf"
- **Localized strings**: Tum UI stringleri String(localized:) ile, TR ve EN destegi
- **Tab navigation**: iOS 17+ Tab API kullanildi

## Notlar

- Xcode projesi SPM uzerinden yonetilir. `xcodebuild` ile build icin `Package.swift` kullanilir
- Domain katmanlarinda Data/Presentation'dan import YOKTUR (izolasyon saglanmis)
- Tum ViewModel'ler `@Observable` + `@MainActor` pattern'i ile olusturulmus
- Tum View dosyalarinda `#Preview` blogu mevcut
- Force unwrap kullanilmamis (AppEnvironment'taki fatal error'lar haric - bu kasitli crash)
- `Any` tipi domain/presentation katmanlarinda kullanilmamis
