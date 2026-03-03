# Developer Handoff: Voice Input (Deepgram STT Streaming)

**Issue**: #28
**Branch**: feature/f4/28-f4-05-voice-input-deepgram-stt-streaming
**Tarih**: 2026-03-03
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/ios/RafRaf/Core/Voice/RFAudioSessionManager.swift` | CREATE | AVAudioSession + AVAudioEngine ses capture yonetimi |
| `apps/ios/RafRaf/Core/Voice/RFSpeechRecognizer.swift` | CREATE | Deepgram WebSocket STT entegrasyonu |
| `apps/ios/RafRaf/Features/VoiceInput/Domain/Models/VoiceInputState.swift` | CREATE | Kayit durumu state machine + hata tipleri |
| `apps/ios/RafRaf/Features/VoiceInput/Domain/Models/TranscriptionResult.swift` | CREATE | Transkripsiyon sonuc + AudioLevel modeli |
| `apps/ios/RafRaf/Features/VoiceInput/Domain/Models/VoiceLanguage.swift` | CREATE | Dil enum'u (TR/EN) |
| `apps/ios/RafRaf/Features/VoiceInput/Domain/Repositories/VoiceInputRepositoryProtocol.swift` | CREATE | Repository protocol |
| `apps/ios/RafRaf/Features/VoiceInput/Domain/UseCases/StartVoiceRecordingUseCase.swift` | CREATE | Kayit baslatma use case |
| `apps/ios/RafRaf/Features/VoiceInput/Domain/UseCases/StopVoiceRecordingUseCase.swift` | CREATE | Kayit durdurma use case |
| `apps/ios/RafRaf/Features/VoiceInput/Data/DTOs/DeepgramMessageDTO.swift` | CREATE | Deepgram JSON mesaj DTO'lari |
| `apps/ios/RafRaf/Features/VoiceInput/Data/Mappers/TranscriptionMapper.swift` | CREATE | DTO -> Domain model mapper |
| `apps/ios/RafRaf/Features/VoiceInput/Data/Repositories/VoiceInputRepositoryImpl.swift` | CREATE | Deepgram WS + ses capture koordinasyonu |
| `apps/ios/RafRaf/Features/VoiceInput/Presentation/ViewModels/VoiceInputViewModel.swift` | CREATE | @Observable + @MainActor ViewModel |
| `apps/ios/RafRaf/Features/VoiceInput/Presentation/Views/RFVoiceInputView.swift` | CREATE | Ana voice input overlay view |
| `apps/ios/RafRaf/Features/VoiceInput/Presentation/Components/RFVoiceInputButton.swift` | CREATE | Mikrofon butonu (tap + long press) |
| `apps/ios/RafRaf/Features/VoiceInput/Presentation/Components/RFWaveformView.swift` | CREATE | Ses dalga formu gostergesi |
| `apps/ios/RafRaf/Features/VoiceInput/Presentation/Components/RFTranscriptionOverlay.swift` | CREATE | Gercek zamanli transkripsiyon gosterimi |
| `apps/ios/RafRaf/Features/VoiceInput/Presentation/Components/RFLanguageSelector.swift` | CREATE | TR/EN dil secimi |
| `apps/ios/RafRaf/Core/DI/AppContainer.swift` | MODIFY | VoiceInput DI kayitlari eklendi |

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| swiftlint | SKIP | CI ortaminda calistirilacak |
| xcodebuild build | SKIP | CI ortaminda calistirilacak |
| xcodebuild test | SKIP | CI ortaminda calistirilacak |

## API Kontrat Uyumu

- `shared/api-contracts/ws/voice-input-messages.json` referans alindi
- Deepgram WS URL, query params ve mesaj formatlari kontrat ile uyumlu
- Mevcut `chat.send` WS mesaji ile final transkripsiyon gonderimi uyumlu

## Notlar

- **Clean Architecture**: Domain katmani Data/Presentation'dan izole. Repository protocol-based.
- **RF* componentler**: Tum UI bilesenlerinde RF* prefix kullanildi (RFVoiceInputButton, RFWaveformView, vb.)
- **Localized strings**: Tum kullanici-gorunur stringler `String(localized:)` ile
- **#Preview**: Her view/component dosyasinda Preview blogu mevcut
- **Factory DI**: AppContainer'a voice input kayitlari eklendi
- **Thread safety**: AVAudioEngine callback'leri audio thread'de, UI guncellemeleri @MainActor uzerinde
- **Force unwrap**: Hicbir dosyada force unwrap yok (#Preview haric)
- **`Any` tipi**: Hicbir public API'da kullanilmamis
- **Deepgram API Key**: Keychain'de saklanir, hardcode edilmemis
