# Developer Handoff: Voice Output (OpenAI TTS Playback)

**Issue**: #29
**Branch**: feature/f4/29-f4-06-voice-output-openai-tts-playback
**Tarih**: 2026-03-03
**Sonraki Agent**: tester (standard pipeline)

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/ios/RafRaf/Features/VoiceOutput/Domain/Models/VoiceOutputState.swift` | CREATE | Oynatma durumu state machine ve hata tipleri |
| `apps/ios/RafRaf/Features/VoiceOutput/Domain/Models/TTSVoice.swift` | CREATE | TTS ses secenekleri enum (alloy, echo, fable, onyx, nova, shimmer) |
| `apps/ios/RafRaf/Features/VoiceOutput/Domain/Models/TTSRequest.swift` | CREATE | TTS istegi domain modeli (text, voice, speed) |
| `apps/ios/RafRaf/Features/VoiceOutput/Domain/Models/TTSAudioResult.swift` | CREATE | TTS ses sonucu domain modeli |
| `apps/ios/RafRaf/Features/VoiceOutput/Domain/Repositories/VoiceOutputRepositoryProtocol.swift` | CREATE | Repository protokolu - synthesize, cache, clear |
| `apps/ios/RafRaf/Features/VoiceOutput/Domain/UseCases/SynthesizeSpeechUseCase.swift` | CREATE | Ses sentezi use case - cache-first strateji |
| `apps/ios/RafRaf/Features/VoiceOutput/Domain/UseCases/StopPlaybackUseCase.swift` | CREATE | Oynatma durdurma + VoiceAudioPlayerProtocol |
| `apps/ios/RafRaf/Features/VoiceOutput/Data/DTOs/TTSRequestDTO.swift` | CREATE | TTS API istek DTO |
| `apps/ios/RafRaf/Features/VoiceOutput/Data/Mappers/TTSMapper.swift` | CREATE | Domain <-> DTO donusumleri |
| `apps/ios/RafRaf/Features/VoiceOutput/Data/Repositories/VoiceAudioPlayer.swift` | CREATE | AVAudioPlayer tabanli ses oynatici |
| `apps/ios/RafRaf/Features/VoiceOutput/Data/Repositories/TTSAudioCache.swift` | CREATE | NSCache + disk cache (2 katmanli) |
| `apps/ios/RafRaf/Features/VoiceOutput/Data/Repositories/VoiceOutputRepositoryImpl.swift` | CREATE | Repository impl - NetworkClient ile TTS API |
| `apps/ios/RafRaf/Features/VoiceOutput/Presentation/ViewModels/VoiceOutputViewModel.swift` | CREATE | @Observable ViewModel - speak, pause, resume, stop, voice/speed ayarlari |
| `apps/ios/RafRaf/Features/VoiceOutput/Presentation/Views/RFVoiceOutputView.swift` | CREATE | Ana voice output ayar ve kontrol ekrani |
| `apps/ios/RafRaf/Features/VoiceOutput/Presentation/Components/RFPlaybackButton.swift` | CREATE | Oynat/duraklat/durdur butonu |
| `apps/ios/RafRaf/Features/VoiceOutput/Presentation/Components/RFPlaybackProgressBar.swift` | CREATE | Oynatma ilerleme cubugu |
| `apps/ios/RafRaf/Features/VoiceOutput/Presentation/Components/RFVoiceSelector.swift` | CREATE | TTS ses secimi chip listesi |
| `apps/ios/RafRaf/Features/VoiceOutput/Presentation/Components/RFSpeedControl.swift` | CREATE | Oynatma hizi preset butonlari |
| `apps/ios/RafRaf/Core/Networking/NetworkClient.swift` | MODIFY | postRawData + executeRaw eklendi (binary response) |
| `apps/ios/RafRaf/Core/DI/AppContainer.swift` | MODIFY | VoiceOutput DI kayitlari eklendi |

## API Kontrat Uyumu

- TTS icin henuz backend API kontrati yok (shared/api-contracts/ icinde). Backend TTS proxy endpoint'i sonraki fazda eklenecek.
- NetworkClient'a eklenen `postRawData` metodu binary response (MP3) icin kullanilacak.
- Endpoint yolu: `/api/v1/tts/synthesize` (backend implementasyonunda olusturulacak)

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| swift build (iOS sim) | PASS | Sifir hata, sifir warning (yeni kod) |
| Mevcut testler (compile) | PASS | Tum mevcut testler derlendi |

## Notlar

- Clean Architecture 3 katmanli mimari korundu (Data/Domain/Presentation)
- Tum domain modeller immutable struct
- VoiceAudioPlayerProtocol domain katmaninda tanimlandi, VoiceAudioPlayer data katmaninda implemente edildi
- NSLock yerine sync helper method kullanildi (Swift 6 concurrency uyumu)
- TTSAudioCache: memory (NSCache, 50MB) + disk (FileManager, 200MB) iki katmanli cache, 7 gun TTL
- AVAudioPlayer rate limiti 0.5-2.0, request speed 0.25-4.0 arasi (clamp uygulanir)
- UserDefaults ile ses, hiz ve autoplay tercihleri persist edilir
- RF* component kurallarina uyuldu: RFText, RFButton, RFColors, RFSpacing kullanildi
- Tum kullanici-gorunur stringler localized: String(localized:)
- Her view dosyasinda #Preview blogu mevcut
- Backend TTS proxy endpoint'i henuz yok; iOS kodu hazir, backend eklenince calisacak
