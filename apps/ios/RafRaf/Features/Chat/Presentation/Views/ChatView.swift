import SwiftUI

/// Sohbet ekrani.
/// Kullanicinin AI asistan ile sesli ve metin tabanli iletisim kurdugu ekran.
struct ChatView: View {
    @State private var viewModel = ChatViewModel()

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading {
                    RFLoadingView(
                        message: String(localized: "chat.loading")
                    )
                } else {
                    contentView
                }
            }
            .navigationTitle(String(localized: "chat.title"))
        }
    }

    @ViewBuilder
    private var contentView: some View {
        VStack(spacing: 0) {
            // Mesaj listesi alani
            ScrollView {
                RFEmptyStateView(
                    systemImage: "message",
                    title: String(localized: "chat.empty.title"),
                    message: String(localized: "chat.empty.message")
                )
            }

            // Mesaj girisi alani
            messageInputView
        }
    }

    private var messageInputView: some View {
        HStack(spacing: RFSpacing.xs) {
            RFTextField(
                String(localized: "chat.input.placeholder"),
                text: $viewModel.messageText
            )

            RFButton(
                String(localized: "chat.send"),
                style: .primary,
                size: .small,
                isDisabled: viewModel.messageText.isEmpty
            ) {
                Task {
                    await viewModel.sendMessage()
                }
            }
        }
        .padding(RFSpacing.md)
        .background(RFColors.fallbackSurface)
    }
}

#Preview {
    ChatView()
}
