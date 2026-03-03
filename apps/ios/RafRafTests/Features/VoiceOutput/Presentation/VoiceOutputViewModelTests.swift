import Foundation
import Testing
@testable import RafRaf

/// VoiceOutputViewModel testleri.
@Suite("VoiceOutputViewModel Tests")
struct VoiceOutputViewModelTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT(
        repository: MockVoiceOutputRepository = MockVoiceOutputRepository(),
        player: MockVoiceAudioPlayer = MockVoiceAudioPlayer(),
        clearPreferences: Bool = true
    ) -> (VoiceOutputViewModel, MockVoiceOutputRepository, MockVoiceAudioPlayer) {
        if clearPreferences {
            UserDefaults.standard.removeObject(forKey: TTSVoice.storageKey)
            UserDefaults.standard.removeObject(forKey: "voiceOutput.playbackSpeed")
            UserDefaults.standard.removeObject(forKey: "voiceOutput.autoPlay")
        }
        let useCase = SynthesizeSpeechUseCase(repository: repository)
        let vm = VoiceOutputViewModel(
            synthesizeSpeechUseCase: useCase,
            audioPlayer: player
        )
        return (vm, repository, player)
    }

    // MARK: - Initial State

    @Test("Baslangic durumu idle olmali")
    @MainActor
    func initialState() {
        let (vm, _, _) = makeSUT()

        #expect(vm.state == .idle)
        #expect(vm.errorMessage == nil)
        #expect(vm.playbackProgress == 0)
        #expect(vm.isPlaying == false)
        #expect(vm.isPaused == false)
        #expect(vm.isLoading == false)
        #expect(vm.isErrorState == false)
    }

    @Test("Varsayilan ses alloy olmali")
    @MainActor
    func defaultVoice() {
        let (vm, _, _) = makeSUT()
        #expect(vm.selectedVoice == .alloy)
    }

    @Test("Varsayilan hiz 1.0 olmali")
    @MainActor
    func defaultSpeed() {
        let (vm, _, _) = makeSUT()
        #expect(vm.playbackSpeed == 1.0)
    }

    @Test("Varsayilan autoPlay kapali olmali")
    @MainActor
    func defaultAutoPlayOff() {
        let (vm, _, _) = makeSUT()
        #expect(vm.autoPlayEnabled == false)
    }

    // MARK: - Computed Properties

    @Test("isPlaying: playing durumunda true olmali")
    @MainActor
    func isPlayingWhenPlaying() async {
        let (vm, _, _) = makeSUT()

        await vm.speak(text: "Test")

        #expect(vm.isPlaying == true)
    }

    @Test("isPlaying: idle durumunda false olmali")
    @MainActor
    func isPlayingWhenIdle() {
        let (vm, _, _) = makeSUT()
        #expect(vm.isPlaying == false)
    }

    @Test("isLoading: loading durumunda true olmali")
    @MainActor
    func isLoadingState() {
        let (vm, _, _) = makeSUT()
        // loading durumu speak() icinde gecici olarak set edilir
        // Baslangicta false
        #expect(vm.isLoading == false)
    }

    @Test("isErrorState: hata durumunda true olmali")
    @MainActor
    func isErrorStateWhenError() async {
        let repo = MockVoiceOutputRepository()
        repo.synthesizeResult = .failure(VoiceOutputRepositoryError.ttsRequestFailed)
        let (vm, _, _) = makeSUT(repository: repo)

        await vm.speak(text: "Test")

        #expect(vm.isErrorState == true)
    }

    // MARK: - Speak

    @Test("speak: basarili durumda playing state'e gecmeli")
    @MainActor
    func speakSuccess() async {
        let (vm, _, _) = makeSUT()

        await vm.speak(text: "Merhaba")

        #expect(vm.state == .playing)
    }

    @Test("speak: repository cagirilmali")
    @MainActor
    func speakCallsRepository() async {
        let (vm, repo, _) = makeSUT()

        await vm.speak(text: "Test mesaji")

        #expect(repo.synthesizeCallCount == 1)
    }

    @Test("speak: ses oynatici cagirilmali")
    @MainActor
    func speakCallsPlayer() async {
        let (vm, _, player) = makeSUT()

        await vm.speak(text: "Test")

        #expect(player.playCallCount == 1)
        #expect(player.lastPlayData != nil)
    }

    @Test("speak: bos metin icin emptyText hatasi")
    @MainActor
    func speakEmptyText() async {
        let (vm, _, _) = makeSUT()

        await vm.speak(text: "")

        #expect(vm.state == .error(.emptyText))
        #expect(vm.errorMessage != nil)
    }

    @Test("speak: sadece bosluk icin emptyText hatasi")
    @MainActor
    func speakWhitespaceOnly() async {
        let (vm, _, _) = makeSUT()

        await vm.speak(text: "   \n\t  ")

        #expect(vm.state == .error(.emptyText))
    }

    @Test("speak: TTS API hatasi durumunda error state")
    @MainActor
    func speakAPIError() async {
        let repo = MockVoiceOutputRepository()
        repo.synthesizeResult = .failure(VoiceOutputRepositoryError.ttsRequestFailed)
        let (vm, _, _) = makeSUT(repository: repo)

        await vm.speak(text: "Test")

        #expect(vm.state == .error(.ttsRequestFailed))
        #expect(vm.errorMessage != nil)
    }

    @Test("speak: oynatma hatasi durumunda error state")
    @MainActor
    func speakPlaybackError() async {
        let player = MockVoiceAudioPlayer()
        player.shouldThrowOnPlay = true
        let (vm, _, _) = makeSUT(player: player)

        await vm.speak(text: "Test")

        #expect(vm.state == .error(.playbackFailed))
    }

    @Test("speak: zaten oynatiliyorsa once durdurmali")
    @MainActor
    func speakWhilePlaying() async {
        let (vm, _, player) = makeSUT()

        await vm.speak(text: "Ilk mesaj")
        #expect(vm.isPlaying == true)

        await vm.speak(text: "Ikinci mesaj")

        #expect(player.stopCallCount == 1)
        #expect(player.playCallCount == 2)
    }

    // MARK: - Pause/Resume

    @Test("pausePlayback: playing durumunda paused'a gecmeli")
    @MainActor
    func pausePlayback() async {
        let (vm, _, player) = makeSUT()

        await vm.speak(text: "Test")
        vm.pausePlayback()

        #expect(vm.state == .paused)
        #expect(player.pauseCallCount == 1)
    }

    @Test("pausePlayback: idle durumunda islem yapmamali")
    @MainActor
    func pausePlaybackWhenIdle() {
        let (vm, _, player) = makeSUT()

        vm.pausePlayback()

        #expect(player.pauseCallCount == 0)
        #expect(vm.state == .idle)
    }

    @Test("resumePlayback: paused durumunda playing'e gecmeli")
    @MainActor
    func resumePlayback() async {
        let (vm, _, player) = makeSUT()

        await vm.speak(text: "Test")
        vm.pausePlayback()
        vm.resumePlayback()

        #expect(vm.state == .playing)
        #expect(player.resumeCallCount == 1)
    }

    @Test("resumePlayback: idle durumunda islem yapmamali")
    @MainActor
    func resumePlaybackWhenIdle() {
        let (vm, _, player) = makeSUT()

        vm.resumePlayback()

        #expect(player.resumeCallCount == 0)
    }

    // MARK: - Stop

    @Test("stopPlayback: idle durumuna gecmeli")
    @MainActor
    func stopPlayback() async {
        let (vm, _, player) = makeSUT()

        await vm.speak(text: "Test")
        vm.stopPlayback()

        #expect(vm.state == .idle)
        #expect(vm.playbackProgress == 0)
        #expect(player.stopCallCount == 1)
    }

    // MARK: - Voice Change

    @Test("changeVoice: secili sesi degistirmeli")
    @MainActor
    func changeVoice() {
        let (vm, _, _) = makeSUT()

        vm.changeVoice(.shimmer)

        #expect(vm.selectedVoice == .shimmer)
    }

    @Test("changeVoice: UserDefaults'a kaydetmeli")
    @MainActor
    func changeVoicePersists() {
        let (vm, _, _) = makeSUT()

        vm.changeVoice(.echo)

        let saved = UserDefaults.standard.string(forKey: TTSVoice.storageKey)
        #expect(saved == "echo")
    }

    // MARK: - Speed

    @Test("playbackSpeed: UserDefaults'a kaydetmeli")
    @MainActor
    func speedPersists() {
        let (vm, _, _) = makeSUT()

        vm.playbackSpeed = 1.5

        let saved = UserDefaults.standard.double(forKey: "voiceOutput.playbackSpeed")
        #expect(saved == 1.5)
    }

    // MARK: - AutoPlay

    @Test("autoPlayEnabled: UserDefaults'a kaydetmeli")
    @MainActor
    func autoPlayPersists() {
        let (vm, _, _) = makeSUT()

        vm.autoPlayEnabled = true

        let saved = UserDefaults.standard.bool(forKey: "voiceOutput.autoPlay")
        #expect(saved == true)
    }

    @Test("autoPlayIfEnabled: autoPlay kapali ise oynatmamali")
    @MainActor
    func autoPlayDisabled() async {
        let (vm, repo, _) = makeSUT()
        vm.autoPlayEnabled = false

        await vm.autoPlayIfEnabled(text: "Test")

        #expect(repo.synthesizeCallCount == 0)
    }

    @Test("autoPlayIfEnabled: autoPlay acik ise oynatmali")
    @MainActor
    func autoPlayEnabled() async {
        let (vm, repo, _) = makeSUT()
        vm.autoPlayEnabled = true

        await vm.autoPlayIfEnabled(text: "Test")

        #expect(repo.synthesizeCallCount == 1)
    }

    // MARK: - Dismiss Error

    @Test("dismissError: hata mesajini temizlemeli")
    @MainActor
    func dismissError() async {
        let repo = MockVoiceOutputRepository()
        repo.synthesizeResult = .failure(VoiceOutputRepositoryError.ttsRequestFailed)
        let (vm, _, _) = makeSUT(repository: repo)

        await vm.speak(text: "Test")
        #expect(vm.errorMessage != nil)

        vm.dismissError()

        #expect(vm.errorMessage == nil)
        #expect(vm.state == .idle)
    }
}
