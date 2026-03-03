# Architect Handoff: iOS Scaffold + Tab Nav + Design System (RF*)

**Issue**: #24
**Faz**: F4
**Tarih**: 2026-03-03
**Sonraki Agent**: developer

## Ozet

iOS uygulamasinin temel iskeleti. Tab navigation, RF* design system base componentleri, color/typography token sistemi, dark mode destegi, Clean Architecture katman yapisi ve DI container. Bu feature tamamen iOS client-side olup backend veya agent katmani degisikligi gerektirmez.

## Feature Spec

-> `shared/feature-specs/f4-24-f4-01-ios-scaffold-tab-nav-design.md`

## API Contracts

Bu feature API endpoint gerektirmez. Kontrat dosyasi olusturulmadi.

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| ios | HIGH | ~15 dosya |
| backend | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- Mevcut iOS scaffold zaten var (F0-05 bagimliliginda olusturulmus). Bu feature mevcut yapilari genisletir.
- RFErrorView yeni olusturulacak component.
- RFCard'a interactive varyant eklenecek (onTap callback).
- RFTextField'a multiline destek eklenecek.
- Tum componentlerde dark mode uyumu saglanmali (RFColors kullanilmali, hardcoded renk YASAK).
- ContentView'daki tab yapisi Chat, Home, Settings olarak 3 tab icerir.
- Factory pattern DI zaten yapilandirilmis (AppContainer.swift). Yeni servislerin eklenmesi gerekebilir.

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu (gerekli degil - iOS-only feature)
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (docs/04_iOS_App_Specification.md)
