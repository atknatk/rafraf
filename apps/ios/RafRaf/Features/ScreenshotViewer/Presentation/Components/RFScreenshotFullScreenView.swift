import NukeUI
import SwiftUI

/// Tam ekran screenshot goruntuleyici.
/// Pinch-to-zoom, pan destegi ile gorseli buyuk ekranda gosterir.
/// Kapat butonu ve baslik bilgisi icerir.
struct RFScreenshotFullScreenView: View {
    let imageURL: URL
    let title: String?
    let onDismiss: () -> Void

    @State private var scale: CGFloat = 1.0
    @State private var offset: CGSize = .zero
    @State private var lastScale: CGFloat = 1.0
    @State private var lastOffset: CGSize = .zero

    private let minScale: CGFloat = 1.0
    private let maxScale: CGFloat = 5.0

    var body: some View {
        ZStack {
            Color.black
                .ignoresSafeArea()

            imageContent

            overlayControls
        }
        .statusBarHidden(true)
    }

    // MARK: - Image Content

    private var imageContent: some View {
        LazyImage(url: imageURL) { state in
            if let image = state.image {
                image
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .scaleEffect(scale)
                    .offset(offset)
                    .gesture(combinedGesture)
                    .onTapGesture(count: 2) {
                        withAnimation(.spring(duration: 0.3)) {
                            doubleTapZoom()
                        }
                    }
                    .animation(.interactiveSpring, value: scale)
                    .animation(.interactiveSpring, value: offset)
            } else if state.error != nil {
                fullScreenErrorView
            } else {
                fullScreenLoadingView
            }
        }
        .ignoresSafeArea()
    }

    // MARK: - Overlay Controls

    private var overlayControls: some View {
        VStack {
            HStack {
                if let title {
                    RFText(title, style: .caption, color: .white)
                        .lineLimit(1)
                }

                Spacer()

                RFButton(
                    String(localized: "screenshotViewer.close"),
                    style: .ghost,
                    size: .small
                ) {
                    onDismiss()
                }
                .foregroundStyle(.white)
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.top, RFSpacing.md)
            .background(
                LinearGradient(
                    colors: [.black.opacity(0.6), .clear],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 80)
                .ignoresSafeArea(edges: .top)
            )

            Spacer()
        }
    }

    // MARK: - Gestures

    private var combinedGesture: some Gesture {
        SimultaneousGesture(magnificationGesture, dragGesture)
    }

    private var magnificationGesture: some Gesture {
        MagnifyGesture()
            .onChanged { value in
                let newScale = lastScale * value.magnification
                scale = min(max(newScale, minScale), maxScale)
            }
            .onEnded { _ in
                lastScale = scale
                if scale <= minScale {
                    withAnimation(.spring(duration: 0.3)) {
                        scale = minScale
                        offset = .zero
                        lastOffset = .zero
                    }
                }
            }
    }

    private var dragGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                guard scale > minScale else { return }
                offset = CGSize(
                    width: lastOffset.width + value.translation.width,
                    height: lastOffset.height + value.translation.height
                )
            }
            .onEnded { _ in
                lastOffset = offset
                if scale <= minScale {
                    withAnimation(.spring(duration: 0.3)) {
                        offset = .zero
                        lastOffset = .zero
                    }
                }
            }
    }

    // MARK: - Double Tap

    private func doubleTapZoom() {
        if scale > minScale {
            scale = minScale
            offset = .zero
            lastScale = minScale
            lastOffset = .zero
        } else {
            scale = 2.5
            lastScale = 2.5
        }
    }

    // MARK: - Subviews

    private var fullScreenLoadingView: some View {
        VStack(spacing: RFSpacing.md) {
            ProgressView()
                .controlSize(.large)
                .tint(.white)
            RFText(
                String(localized: "screenshotViewer.loading"),
                style: .caption,
                color: .white
            )
        }
    }

    private var fullScreenErrorView: some View {
        VStack(spacing: RFSpacing.sm) {
            Image(systemName: "photo.badge.exclamationmark")
                .font(.system(size: 48))
                .foregroundStyle(.white.opacity(0.7))
            RFText(
                String(localized: "screenshotViewer.error.imageLoadFailed"),
                style: .body,
                color: .white.opacity(0.7)
            )
        }
    }
}

#Preview {
    RFScreenshotFullScreenView(
        imageURL: URL(string: "https://picsum.photos/800/600")!,
        title: "Agent Screenshot",
        onDismiss: {}
    )
}
