import SwiftUI

/// Screenshot goruntuleyici ana ekrani.
/// Inline thumbnail + tiklaninca tam ekran modal goruntuleyici acar.
/// Pinch-to-zoom, pan, cift tikla zoom destegi saglar.
struct ScreenshotViewerView: View {
    @State private var viewModel: ScreenshotViewerViewModel

    let imageURL: String
    let title: String?

    init(
        viewModel: ScreenshotViewerViewModel,
        imageURL: String,
        title: String? = nil
    ) {
        self._viewModel = State(initialValue: viewModel)
        self.imageURL = imageURL
        self.title = title
    }

    var body: some View {
        Group {
            switch viewModel.viewerState {
            case .loading:
                RFLoadingView(
                    message: String(localized: "screenshotViewer.loading")
                )
            case .loaded:
                screenshotContent
            case .error(let message):
                RFErrorView(
                    message: message,
                    retryTitle: String(localized: "screenshotViewer.retry")
                ) {
                    Task {
                        await viewModel.retry()
                    }
                }
            }
        }
        .onAppear {
            viewModel.loadFromURL(url: imageURL)
        }
        .fullScreenCover(isPresented: $viewModel.isFullScreen) {
            if let url = URL(string: imageURL) {
                RFScreenshotFullScreenView(
                    imageURL: url,
                    title: title ?? viewModel.screenshot?.title,
                    onDismiss: {
                        viewModel.dismissFullScreen()
                    }
                )
            }
        }
    }

    // MARK: - Screenshot Content

    @ViewBuilder
    private var screenshotContent: some View {
        if let url = URL(string: imageURL) {
            RFCard(
                style: .interactive,
                padding: 0,
                cornerRadius: 12,
                onTap: {
                    viewModel.toggleFullScreen()
                }
            ) {
                VStack(spacing: 0) {
                    RFScreenshotViewer(
                        imageURL: url,
                        scale: $viewModel.currentScale,
                        offset: $viewModel.currentOffset,
                        minScale: viewModel.minScale,
                        maxScale: viewModel.maxScale,
                        onDoubleTap: {
                            viewModel.doubleTapZoom()
                        }
                    )
                    .frame(maxWidth: .infinity, maxHeight: 300)

                    if let screenshotTitle = title ?? viewModel.screenshot?.title {
                        HStack {
                            RFText(
                                screenshotTitle,
                                style: .caption
                            )
                            .lineLimit(1)

                            Spacer()

                            Image(systemName: "arrow.up.left.and.arrow.down.right")
                                .font(.caption)
                                .foregroundStyle(RFColors.fallbackTextSecondary)
                        }
                        .padding(.horizontal, RFSpacing.sm)
                        .padding(.vertical, RFSpacing.xs)
                    }
                }
            }
        } else {
            RFErrorView(
                message: String(localized: "screenshotViewer.error.invalidURL")
            )
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        ScreenshotViewerView(
            viewModel: ScreenshotViewerViewModel(
                loadScreenshotUseCase: LoadScreenshotUseCase(
                    repository: PreviewScreenshotRepository()
                )
            ),
            imageURL: "https://picsum.photos/800/600",
            title: "Agent Screenshot"
        )

        ScreenshotViewerView(
            viewModel: ScreenshotViewerViewModel(
                loadScreenshotUseCase: LoadScreenshotUseCase(
                    repository: PreviewScreenshotRepository()
                )
            ),
            imageURL: "invalid-url"
        )
    }
    .padding()
}

/// Preview icin mock repository.
private struct PreviewScreenshotRepository: ScreenshotRepositoryProtocol {
    func fetchScreenshot(by screenshotId: String) async throws -> Screenshot {
        Screenshot(
            url: "https://picsum.photos/800/600",
            title: "Preview Screenshot"
        )
    }

    func getPreSignedURL(for originalURL: String) async throws -> String {
        originalURL
    }
}
