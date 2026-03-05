import NukeUI
import SwiftUI

/// RafRaf screenshot goruntuleyici bileseni.
/// Pinch-to-zoom, pan ve cift tikla zoom destegi ile gorselleri goruntular.
/// Nuke kutuphanesi ile async image loading yapar.
struct RFScreenshotViewer: View {
    let imageURL: URL
    @Binding var scale: CGFloat
    @Binding var offset: CGSize
    let minScale: CGFloat
    let maxScale: CGFloat
    let onDoubleTap: () -> Void

    @State private var lastScale: CGFloat = 1.0
    @State private var lastOffset: CGSize = .zero

    init(
        imageURL: URL,
        scale: Binding<CGFloat>,
        offset: Binding<CGSize>,
        minScale: CGFloat = 1.0,
        maxScale: CGFloat = 5.0,
        onDoubleTap: @escaping () -> Void = {}
    ) {
        self.imageURL = imageURL
        self._scale = scale
        self._offset = offset
        self.minScale = minScale
        self.maxScale = maxScale
        self.onDoubleTap = onDoubleTap
    }

    var body: some View {
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
                            onDoubleTap()
                        }
                    }
                    .animation(.interactiveSpring, value: scale)
                    .animation(.interactiveSpring, value: offset)
            } else if state.error != nil {
                screenshotErrorView
            } else {
                screenshotLoadingView
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
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

    // MARK: - Subviews

    private var screenshotLoadingView: some View {
        VStack(spacing: RFSpacing.md) {
            ProgressView()
                .controlSize(.large)
            RFText(
                String(localized: "screenshotViewer.loading"),
                style: .caption
            )
        }
        .frame(maxWidth: .infinity, minHeight: 200)
        .background(RFColors.fallbackSurface)
    }

    private var screenshotErrorView: some View {
        VStack(spacing: RFSpacing.sm) {
            Image(systemName: "photo.badge.exclamationmark")
                .font(.system(size: 36))
                .foregroundStyle(RFColors.error)
            RFText(
                String(localized: "screenshotViewer.error.imageLoadFailed"),
                style: .caption,
                color: RFColors.error
            )
        }
        .frame(maxWidth: .infinity, minHeight: 200)
        .background(RFColors.fallbackSurface)
    }
}

// swiftlint:disable force_unwrapping
#Preview {
    RFScreenshotViewer(
        imageURL: URL(string: "https://picsum.photos/800/600")!,
        scale: .constant(1.0),
        offset: .constant(.zero)
    )
    .padding()
}
