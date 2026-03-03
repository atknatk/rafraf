import Foundation
import Testing
@testable import RafRaf

/// VoiceInputViewModel testleri.
@Suite("VoiceInputViewModel Tests")
struct VoiceInputViewModelTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT(
        repository: MockVoiceInputRepository = MockVoiceInputRepository()
    ) -> (VoiceInputViewModel, MockVoiceInputRepository) {
        let audioManager = RFAudioSessionManager()
        let vm = VoiceInputViewModel(
            startRecordingUseCase: StartVoiceRecordingUseCase(repository: repository),
            stopRecordingUseCase: StopVoiceRecordingUseCase(repository: repository),
            audioSessionManager: audioManager
        )
        return (vm, repository)
    }

    // MARK: - Initial State

    @Test("Baslangic durumu idle olmali")
    @MainActor
    func initialState() {
        let (vm, _) = makeSUT()

        #expect(vm.state == .idle)
        #expect(vm.interimTranscription.isEmpty)
        #expect(vm.finalTranscription.isEmpty)
        #expect(vm.errorMessage == nil)
        #expect(vm.isRecording == false)
        #expect(vm.isErrorState == false)
    }

    @Test("Varsayilan dil Turkce olmali")
    @MainActor
    func defaultLanguageTurkish() {
        let (vm, _) = makeSUT()

        #expect(vm.selectedLanguage == .turkish)
    }

    // MARK: - isRecording computed property

    @Test("isRecording: recording durumunda true olmali")
    @MainActor
    func isRecordingWhenRecording() async {
        let repo = MockVoiceInputRepository()
        let stream = repo.makeControllableStream()
        repo.startStreamingResult = .success(stream)
        let (vm, _) = makeSUT(repository: repo)

        await vm.startRecording()

        #expect(vm.isRecording == true)
    }

    @Test("isRecording: idle durumunda false olmali")
    @MainActor
    func isRecordingWhenIdle() {
        let (vm, _) = makeSUT()

        #expect(vm.isRecording == false)
    }

    // MARK: - isErrorState computed property

    @Test("isErrorState: hata durumunda true olmali")
    @MainActor
    func isErrorStateWhenError() async {
        let repo = MockVoiceInputRepository()
        repo.startStreamingResult = .failure(VoiceInputRepositoryError.connectionFailed)
        let (vm, _) = makeSUT(repository: repo)

        await vm.startRecording()

        #expect(vm.isErrorState == true)
    }

    // MARK: - Start Recording

    @Test("startRecording: repository cagirilmali")
    @MainActor
    func startRecordingCallsRepository() async {
        let repo = MockVoiceInputRepository()
        let stream = repo.makeControllableStream()
        repo.startStreamingResult = .success(stream)
        let (vm, _) = makeSUT(repository: repo)

        await vm.startRecording()

        #expect(repo.startStreamingCallCount == 1)
    }

    @Test("startRecording: secili dil repository'ye iletilmeli")
    @MainActor
    func startRecordingPassesLanguage() async {
        let repo = MockVoiceInputRepository()
        let stream = repo.makeControllableStream()
        repo.startStreamingResult = .success(stream)
        let (vm, _) = makeSUT(repository: repo)

        vm.changeLanguage(.english)
        await vm.startRecording()

        #expect(repo.lastLanguage == .english)
    }

    @Test("startRecording: baglanti hatasi durumunda error state'e gecmeli")
    @MainActor
    func startRecordingConnectionError() async {
        let repo = MockVoiceInputRepository()
        repo.startStreamingResult = .failure(VoiceInputRepositoryError.connectionFailed)
        let (vm, _) = makeSUT(repository: repo)

        await vm.startRecording()

        #expect(vm.isErrorState == true)
        #expect(vm.errorMessage != nil)
    }

    @Test("startRecording: mikrofon izni hatasi durumunda error state'e gecmeli")
    @MainActor
    func startRecordingMicPermissionError() async {
        let repo = MockVoiceInputRepository()
        repo.startStreamingResult = .failure(VoiceInputRepositoryError.microphonePermissionDenied)
        let (vm, _) = makeSUT(repository: repo)

        await vm.startRecording()

        #expect(vm.state == .error(.microphonePermissionDenied))
    }

    @Test("startRecording: zaten recording durumundaysa tekrar baslatmamali")
    @MainActor
    func startRecordingWhenAlreadyRecording() async {
        let repo = MockVoiceInputRepository()
        let stream = repo.makeControllableStream()
        repo.startStreamingResult = .success(stream)
        let (vm, _) = makeSUT(repository: repo)

        await vm.startRecording()
        await vm.startRecording()  // Ikinci cagri

        #expect(repo.startStreamingCallCount == 1)
    }

    // MARK: - Stop Recording

    @Test("stopRecording: idle durumundaysa islem yapmamali")
    @MainActor
    func stopRecordingWhenIdle() async {
        let repo = MockVoiceInputRepository()
        let (vm, _) = makeSUT(repository: repo)

        await vm.stopRecording()

        #expect(repo.stopStreamingCallCount == 0)
    }

    // MARK: - Cancel Recording

    @Test("cancelRecording: durumu idle'a gecirmeli")
    @MainActor
    func cancelRecordingResetsState() async {
        let repo = MockVoiceInputRepository()
        let stream = repo.makeControllableStream()
        repo.startStreamingResult = .success(stream)
        let (vm, _) = makeSUT(repository: repo)

        await vm.startRecording()
        await vm.cancelRecording()

        #expect(vm.state == .idle)
        #expect(vm.interimTranscription.isEmpty)
    }

    @Test("cancelRecording: stopStreaming cagirilmali")
    @MainActor
    func cancelRecordingCallsStop() async {
        let repo = MockVoiceInputRepository()
        let stream = repo.makeControllableStream()
        repo.startStreamingResult = .success(stream)
        let (vm, _) = makeSUT(repository: repo)

        await vm.startRecording()
        await vm.cancelRecording()

        #expect(repo.stopStreamingCallCount == 1)
    }

    // MARK: - Change Language

    @Test("changeLanguage: secili dili degistirmeli")
    @MainActor
    func changeLanguage() {
        let (vm, _) = makeSUT()

        vm.changeLanguage(.english)

        #expect(vm.selectedLanguage == .english)
    }

    // MARK: - Dismiss Error

    @Test("dismissError: hata mesajini temizlemeli")
    @MainActor
    func dismissError() async {
        let repo = MockVoiceInputRepository()
        repo.startStreamingResult = .failure(VoiceInputRepositoryError.connectionFailed)
        let (vm, _) = makeSUT(repository: repo)

        await vm.startRecording()
        #expect(vm.errorMessage != nil)

        vm.dismissError()

        #expect(vm.errorMessage == nil)
        #expect(vm.state == .idle)
    }

    // MARK: - Transcription Callback

    @Test("onTranscriptionComplete: callback ayarlanabilmeli")
    @MainActor
    func onTranscriptionCompleteCallback() {
        let (vm, _) = makeSUT()
        var receivedText: String?

        vm.onTranscriptionComplete = { text in
            receivedText = text
        }

        // Callback atandi, nil degil
        #expect(vm.onTranscriptionComplete != nil)
        // Henuz cagirilmadi
        #expect(receivedText == nil)
    }
}
