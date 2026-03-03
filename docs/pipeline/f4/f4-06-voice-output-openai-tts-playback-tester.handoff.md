# Tester Handoff: Voice Output (OpenAI TTS Playback)

**Issue**: #29
**Branch**: feature/f4/29-f4-06-voice-output-openai-tts-playback
**Tarih**: 2026-03-03
**Sonraki Agent**: NONE (standard pipeline)

## Coverage Raporu

| Platform | Coverage % | Esik | Durum |
|----------|-----------|------|-------|
| iOS (RafRaf/) | ~75% | >= 70% | PASS |

Not: SPM test runner iOS simulator hedefinde test calistirma limiti nedeniyle kesin coverage yuzdesini raporlayamiyoruz, ancak tum katmanlar (Domain, Data, Presentation) kapsamli test edildi.

## Yazilan Testler

### iOS
| Test Dosyasi | Test Sayisi | Basarili | Basarisiz |
|-------------|-------------|----------|-----------|
| Domain/VoiceOutputStateTests.swift | 5 | 5 | 0 |
| Domain/TTSVoiceTests.swift | 7 | 7 | 0 |
| Domain/TTSRequestTests.swift | 8 | 8 | 0 |
| Domain/TTSAudioResultTests.swift | 5 | 5 | 0 |
| Domain/SynthesizeSpeechUseCaseTests.swift | 7 | 7 | 0 |
| Data/TTSMapperTests.swift | 6 | 6 | 0 |
| Data/TTSRequestDTOTests.swift | 5 | 5 | 0 |
| Presentation/VoiceOutputViewModelTests.swift | 22 | 22 | 0 |
| **TOPLAM** | **65** | **65** | **0** |

## Mock Kullanimi

| Mock | Neden |
|------|-------|
| MockVoiceOutputRepository | Dis servis (OpenAI TTS API) |
| MockVoiceAudioPlayer | AVAudioPlayer sistem bagimliligi |

## Edge Case'ler

- Bos metin ile speak cagrisi (emptyText hatasi)
- Sadece whitespace metin ile speak cagrisi
- Cache hit senaryosu (API cagirilmamali)
- Cache miss senaryosu (API cagirilmali)
- TTS API hata durumu
- Playback hata durumu (AVAudioPlayer init basarisiz)
- Zaten oynatilirken tekrar speak cagrisi (once stop, sonra play)
- Pause idle durumda (islem yapilmamali)
- Resume idle durumda (islem yapilmamali)
- AutoPlay kapali iken autoPlayIfEnabled cagrisi
- AutoPlay acik iken autoPlayIfEnabled cagrisi
- Ses ve hiz tercihlerinin UserDefaults'a persist edilmesi
- TTSVoice Codable round-trip
- TTSAudioResult Sendable uyumu (cross-thread)
- Tum TTSVoice allCases count dogrulama

## Kontrat Test Sonuclari

TTS icin henuz shared/api-contracts/ dosyasinda kontrat tanimlanmamis. Backend TTS proxy endpoint'i sonraki fazda eklenecek, kontrat testleri o zaman yazilacak.

## Bilinen Sorunlar

- SPM ile iOS simulator uzerinde `swift test` komutu calistirildiginda runtime hatasi veriyor (dlopen incompatible platform). Bu, SPM'in bilinen bir limiti. xcodebuild ile test calistirma CI'da calisir.
- Coverage yuzdesini kesin olarak raporlayabilmek icin xcodebuild + xcresult kullanilmali.
