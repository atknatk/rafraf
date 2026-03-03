# Feature: Voice Input (Deepgram STT Streaming)

**Issue**: #28
**Faz**: F4
**Katmanlar**: ios
**Pipeline**: full
**Tarih**: 2026-03-03

## Ozet

Sesli giris ozelligi. Kullanici mikrofon butonuna basarak sesli mesaj gonderebilir. AVAudioEngine ile ses capture edilir, Deepgram WebSocket API uzerinden gercek zamanli speech-to-text donusumu yapilir. Interim sonuclar ekranda anlik gosterilir, final transkripsiyon chat mesaji olarak backend'e iletilir. Push-to-talk (default) ve toggle modlari desteklenir. Dil secimi (TR/EN) ve ses seviyesi gostergesi (waveform) icerir.

## Degisecek Dosyalar

### iOS (`apps/ios/`)

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `RafRaf/Core/Voice/RFAudioSessionManager.swift` | CREATE | AVAudioSession yapilandirma ve yonetimi |
| `RafRaf/Core/Voice/RFSpeechRecognizer.swift` | CREATE | Deepgram WebSocket STT entegrasyonu |
| `RafRaf/Features/VoiceInput/Domain/Models/VoiceInputState.swift` | CREATE | Ses kayit durumu domain modeli |
| `RafRaf/Features/VoiceInput/Domain/Models/TranscriptionResult.swift` | CREATE | Transkripsiyon sonuc modeli (interim/final) |
| `RafRaf/Features/VoiceInput/Domain/Models/VoiceLanguage.swift` | CREATE | Desteklenen dil enum'u (TR/EN) |
| `RafRaf/Features/VoiceInput/Domain/Repositories/VoiceInputRepositoryProtocol.swift` | CREATE | Voice input repository protocol |
| `RafRaf/Features/VoiceInput/Domain/UseCases/StartVoiceRecordingUseCase.swift` | CREATE | Ses kaydi baslat use case |
| `RafRaf/Features/VoiceInput/Domain/UseCases/StopVoiceRecordingUseCase.swift` | CREATE | Ses kaydi durdur use case |
| `RafRaf/Features/VoiceInput/Data/DTOs/DeepgramMessageDTO.swift` | CREATE | Deepgram WS mesaj DTO'lari |
| `RafRaf/Features/VoiceInput/Data/Mappers/TranscriptionMapper.swift` | CREATE | Deepgram DTO -> Domain model mapper |
| `RafRaf/Features/VoiceInput/Data/Repositories/VoiceInputRepositoryImpl.swift` | CREATE | Deepgram WS baglanti + ses streaming impl |
| `RafRaf/Features/VoiceInput/Presentation/ViewModels/VoiceInputViewModel.swift` | CREATE | @Observable + @MainActor ViewModel |
| `RafRaf/Features/VoiceInput/Presentation/Views/RFVoiceInputView.swift` | CREATE | Ana voice input overlay ekrani |
| `RafRaf/Features/VoiceInput/Presentation/Components/RFVoiceInputButton.swift` | CREATE | Mikrofon butonu (toggle + press-and-hold) |
| `RafRaf/Features/VoiceInput/Presentation/Components/RFWaveformView.swift` | CREATE | Ses seviyesi dalga formu gostergesi |
| `RafRaf/Features/VoiceInput/Presentation/Components/RFTranscriptionOverlay.swift` | CREATE | Gercek zamanli transkripsiyon gosterimi |
| `RafRaf/Features/VoiceInput/Presentation/Components/RFLanguageSelector.swift` | CREATE | Dil secim bilesei (TR/EN) |

## API Endpoints

### REST

Bu feature yeni REST endpoint EKLEMEZ. Ses verisi dogrudan Deepgram WebSocket API'a gonderilir. Final transkripsiyon mevcut chat.send WS mesaji ile backend'e iletilir.

### WebSocket Messages

Deepgram ile dogrudan WebSocket baglantisi kurulur (iOS -> Deepgram). Backend uzerinden gecmez.

| Direction | Type | Payload | Aciklama |
|-----------|------|---------|----------|
| iOS -> Deepgram | binary | raw audio bytes | Linear PCM, 16kHz, mono ses verisi |
| Deepgram -> iOS | JSON | `DeepgramTranscriptResponse` | Interim/final transkripsiyon sonucu |
| iOS -> Backend (mevcut) | `chat.send` | `ChatSendPayload` | Final transkripsiyon text olarak gonderilir |

## Data Model

### Swift Models

```swift
// Domain Model - VoiceInputState
enum VoiceInputState: Sendable, Equatable {
    case idle
    case requesting         // Mikrofon izni isteniyor
    case recording          // Ses kaydediliyor
    case processing         // Son parcalar isleniyor
    case error(VoiceInputError)
}

// Domain Model - VoiceInputError
enum VoiceInputError: Sendable, Equatable {
    case microphonePermissionDenied
    case deepgramConnectionFailed
    case networkUnavailable
    case audioSessionError
    case transcriptionFailed
}

// Domain Model - TranscriptionResult
struct TranscriptionResult: Sendable, Equatable {
    let text: String
    let isFinal: Bool
    let confidence: Double
    let language: VoiceLanguage
}

// Domain Model - VoiceLanguage
enum VoiceLanguage: String, Sendable, CaseIterable {
    case turkish = "tr"
    case english = "en"
}

// Domain Model - AudioLevel
struct AudioLevel: Sendable, Equatable {
    let averagePower: Float   // -160 to 0 dB
    let peakPower: Float      // -160 to 0 dB
    let normalizedLevel: Float // 0.0 to 1.0
}
```

### Deepgram DTO

```swift
// Data Layer - DeepgramMessageDTO
struct DeepgramTranscriptDTO: Codable, Sendable {
    let type: String              // "Results"
    let channelIndex: [Int]?
    let duration: Double?
    let start: Double?
    let isFinal: Bool
    let speechFinal: Bool
    let channel: DeepgramChannelDTO

    enum CodingKeys: String, CodingKey {
        case type
        case channelIndex = "channel_index"
        case duration
        case start
        case isFinal = "is_final"
        case speechFinal = "speech_final"
        case channel
    }
}

struct DeepgramChannelDTO: Codable, Sendable {
    let alternatives: [DeepgramAlternativeDTO]
}

struct DeepgramAlternativeDTO: Codable, Sendable {
    let transcript: String
    let confidence: Double
    let words: [DeepgramWordDTO]?
}

struct DeepgramWordDTO: Codable, Sendable {
    let word: String
    let start: Double
    let end: Double
    let confidence: Double
    let punctuatedWord: String?

    enum CodingKeys: String, CodingKey {
        case word, start, end, confidence
        case punctuatedWord = "punctuated_word"
    }
}
```

## Business Rules

1. **Mikrofon izni**: Ilk kullaninda `AVAudioSession.requestRecordPermission()` cagrilir. Izin verilmezse bilgilendirme gosterilir ve Settings'e yonlendirilir.
2. **Push-to-talk modu (default)**: Kullanici butona basili tutarken kayit yapar, birakinice durdurur ve final transkripsiyon gonderilir.
3. **Toggle modu**: Kullanici butona bir kez dokunur (kayit baslar), tekrar dokunur (kayit durur ve gonderir).
4. **Ses formati**: Linear PCM, 16000 Hz sample rate, 1 kanal (mono), 16-bit.
5. **Deepgram baglanti**: Her kayit oturumu icin yeni WebSocket baglantisi acilir, kayit bitince kapatilir.
6. **Interim sonuclar**: Kullanici ne soyledigini gercek zamanli gorur (gri text). Final sonuc kalici mesaj olarak gosterilir.
7. **Dil secimi**: Varsayilan Turkce (tr). Kullanici EN'ye gecebilir. Secim UserDefaults'ta saklanir.
8. **Ses seviyesi**: AVAudioEngine'den alinan average/peak power degerleri normalize edilerek waveform gosterilir.
9. **Network hatasi**: Deepgram WS baglantisi koparsa kullaniciya hata gosterilir, kayit durdurulur.
10. **Arkaplan davranisi**: App arka plana giderse kayit otomatik durdurulur.
11. **Deepgram config**: model=nova-2, smart_format=true, punctuate=true, interim_results=true, endpointing=500, vad_events=true.
12. **Bos transkripsiyon**: Final transkripsiyon bossa mesaj gonderilmez, kullaniciya "Ses algilanamadi" mesaji gosterilir.

## Test Requirements

### iOS
- [ ] Unit test: VoiceInputViewModel state gecisleri (idle -> recording -> processing -> idle)
- [ ] Unit test: TranscriptionMapper Deepgram DTO -> domain model donusumu
- [ ] Unit test: VoiceLanguage enum dogrulama
- [ ] Unit test: StartVoiceRecordingUseCase / StopVoiceRecordingUseCase
- [ ] Unit test: VoiceInputRepositoryImpl mock Deepgram ile
- [ ] Unit test: AudioLevel normalizasyonu
- [ ] Unit test: Hata durumlari (izin engeli, network, Deepgram hata)
- [ ] Unit test: Bos transkripsiyon senaryosu
- [ ] UI test: Mikrofon butonu gorunurlugu ve etkilesimi

## Acceptance Criteria

- [ ] Mikrofon erisim izni isteme ve yonetme
- [ ] Ses kaydi baslatma/durdurma (push-to-talk + toggle)
- [ ] Deepgram WebSocket ile streaming STT
- [ ] Gercek zamanli transkripsiyon gosterimi (interim results)
- [ ] Ses seviyesi gostergesi (waveform)
- [ ] Dil secimi (TR/EN)
- [ ] Hata handling (mikrofon erisim engeli, network hatasi, Deepgram hatasi)
- [ ] Final transkripsiyon chat.send ile backend'e gonderme
- [ ] Unit testler yazildi
- [ ] Coverage >= 70%
