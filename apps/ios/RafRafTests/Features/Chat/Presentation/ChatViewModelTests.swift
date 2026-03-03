import Foundation
import Testing
@testable import RafRaf

/// ChatViewModel testleri.
@Suite("ChatViewModel Tests")
struct ChatViewModelTests {

    @Test("ChatViewModel baslangic durumu dogru olmali")
    @MainActor
    func initialState() {
        let viewModel = ChatViewModel()

        #expect(viewModel.isLoading == false)
        #expect(viewModel.messageText.isEmpty)
        #expect(viewModel.errorMessage == nil)
    }

    @Test("sendMessage bos mesajda islem yapmamali")
    @MainActor
    func sendMessageEmpty() async {
        let viewModel = ChatViewModel()
        viewModel.messageText = ""

        await viewModel.sendMessage()

        #expect(viewModel.messageText.isEmpty)
    }

    @Test("sendMessage sonrasi messageText temizlenmeli")
    @MainActor
    func sendMessageClearsText() async {
        let viewModel = ChatViewModel()
        viewModel.messageText = "Test mesaji"

        await viewModel.sendMessage()

        #expect(viewModel.messageText.isEmpty)
    }
}
