# Architect Handoff: Voice Input (Deepgram STT Streaming)

**Issue**: #28
**Faz**: F4
**Tarih**: 2026-03-03
**Sonraki Agent**: developer

## Ozet

Sesli giris ozelligi. AVAudioEngine ile ses capture, Deepgram WebSocket API ile gercek zamanli streaming STT, interim/final transkripsiyon gosterimi, ses seviyesi waveform, dil secimi (TR/EN). iOS-only feature — backend degisikligi yok (Deepgram ile dogrudan iOS baglantisi).

## Feature Spec

-> `shared/feature-specs/f4-28-f4-05-voice-input-deepgram-stt-streaming.md`

## API Contracts

-> `shared/api-contracts/ws/voice-input-messages.json` (Deepgram WS mesajlari)

Not: Bu feature backend'e yeni endpoint eklemez. Ses verisi iOS'tan dogrudan Deepgram'a gider. Final transkripsiyon mevcut `chat.send` WS mesaji ile backend'e gonderilir.

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| ios | HIGH | 17 dosya |
| backend | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- **Deepgram API Key**: `DEEPGRAM_API_KEY` environment variable olarak saklanmali. Keychain'de tutulup WS baglantisinda header olarak gonderilmeli.
- **AVAudioSession konfigurasyonu**: `.playAndRecord` category, `.defaultToSpeaker` option, `.allowBluetooth` option.
- **Ses buffer boyutu**: AVAudioEngine tap'ten gelen buffer'lar 4096 frame olarak ayarlanmali (16kHz * 0.256s).
- **Bagimlillik**: F4-04 Chat view (issue #27) tamamlanmis olmali. Chat input bar'daki mikrofon butonu bu feature ile aktif hale gelir.
- **Thread safety**: AVAudioEngine callback'leri audio thread'de gelir, UI guncelemeleri MainActor'e dispatch edilmeli.
- **Deepgram WS auth**: `Authorization: Token <DEEPGRAM_API_KEY>` header'i ile baglanti kurulur.
- **Memory management**: Ses buffer'lari islendikten sonra serbest birakilmali, retain cycle onlenmeli.

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu (Deepgram WS mesajlari)
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (04_iOS_App_Specification.md Section 4.1)
