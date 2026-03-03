import SwiftUI

/// Gorsel mesaj goruntuleme bileseni.
/// Mesaj icerisindeki gorselleri inline gosterir, tiklaninca tam ekran acilir.
struct RFImageMessageView: View {
    let url: String
    let onTap: (() -> Void)?

    init(url: String, onTap: (() -> Void)? = nil) {
        self.url = url
        self.onTap = onTap
    }

    var body: some View {
        RFCard(
            style: .interactive,
            padding: 0,
            cornerRadius: 12,
            onTap: { onTap?() }
        ) {
            imageContent
        }
    }

    @ViewBuilder
    private var imageContent: some View {
        if let imageURL = URL(string: url) {
            AsyncImage(url: imageURL) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(maxWidth: 250, maxHeight: 200)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                case .failure:
                    imagePlaceholder(systemImage: "exclamationmark.triangle", isError: true)
                case .empty:
                    imagePlaceholder(systemImage: "photo", isError: false)
                @unknown default:
                    imagePlaceholder(systemImage: "photo", isError: false)
                }
            }
        } else {
            imagePlaceholder(systemImage: "exclamationmark.triangle", isError: true)
        }
    }

    private func imagePlaceholder(systemImage: String, isError: Bool) -> some View {
        VStack(spacing: RFSpacing.xs) {
            Image(systemName: systemImage)
                .font(.title2)
                .foregroundStyle(
                    isError ? RFColors.error : RFColors.fallbackTextSecondary
                )
            if isError {
                RFText(
                    String(localized: "chat.image.loadError"),
                    style: .caption,
                    color: RFColors.error
                )
            } else {
                ProgressView()
            }
        }
        .frame(width: 200, height: 120)
        .background(RFColors.fallbackSurface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFImageMessageView(
            url: "https://picsum.photos/400/300"
        )

        RFImageMessageView(
            url: "invalid-url"
        )
    }
    .padding()
}
