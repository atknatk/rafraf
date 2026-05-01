import SwiftUI

/// Yatay akis duzeni - kapasite/etiket chip'leri icin.
/// Subview'lar yatay olarak yerlestirilir, container genisligini astiklarinda
/// otomatik olarak yeni satira tasinir.
///
/// Daha once `Features/Project/Presentation/Views/ProjectDetailView.swift`
/// icinde tanimlanmisti; T0.5 (Project feature kaldirilmasi) sirasinda
/// Agent feature tarafindan halen kullanildigi icin Design System'e tasindi.
struct FlowLayout: Layout {
    let spacing: CGFloat

    init(spacing: CGFloat = 8) {
        self.spacing = spacing
    }

    func sizeThatFits(
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) -> CGSize {
        let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        return layout(sizes: sizes, containerWidth: proposal.width ?? .infinity).size
    }

    func placeSubviews(
        in bounds: CGRect,
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) {
        let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        let offsets = layout(sizes: sizes, containerWidth: bounds.width).offsets

        for (index, subview) in subviews.enumerated() {
            subview.place(
                at: CGPoint(
                    x: bounds.minX + offsets[index].x,
                    y: bounds.minY + offsets[index].y
                ),
                proposal: .unspecified
            )
        }
    }

    private func layout(
        sizes: [CGSize],
        containerWidth: CGFloat
    ) -> (offsets: [CGPoint], size: CGSize) {
        var offsets: [CGPoint] = []
        var currentX: CGFloat = 0
        var currentY: CGFloat = 0
        var lineHeight: CGFloat = 0
        var maxWidth: CGFloat = 0

        for size in sizes {
            if currentX + size.width > containerWidth, currentX > 0 {
                currentX = 0
                currentY += lineHeight + spacing
                lineHeight = 0
            }

            offsets.append(CGPoint(x: currentX, y: currentY))
            lineHeight = max(lineHeight, size.height)
            currentX += size.width + spacing
            maxWidth = max(maxWidth, currentX - spacing)
        }

        return (
            offsets: offsets,
            size: CGSize(width: maxWidth, height: currentY + lineHeight)
        )
    }
}
