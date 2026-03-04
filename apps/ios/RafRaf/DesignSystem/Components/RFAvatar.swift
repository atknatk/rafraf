import SwiftUI
import NukeUI

/// RafRaf avatar boyutlari.
enum RFAvatarSize: Sendable {
    case small
    case medium
    case large

    var dimension: CGFloat {
        switch self {
        case .small: return 32
        case .medium: return 44
        case .large: return 64
        }
    }

    var font: Font {
        switch self {
        case .small: return .caption
        case .medium: return .body
        case .large: return .title2
        }
    }

    var onlineIndicatorSize: CGFloat {
        switch self {
        case .small: return 10
        case .medium: return 12
        case .large: return 16
        }
    }
}

/// RafRaf avatar bileseni.
/// Kullanici profil resmi veya bos harf gostergesi.
struct RFAvatar: View {
    let imageURL: URL?
    let name: String
    let size: RFAvatarSize
    let showRing: Bool
    let showOnlineIndicator: Bool

    init(
        imageURL: URL? = nil,
        name: String,
        size: RFAvatarSize = .medium,
        showRing: Bool = false,
        showOnlineIndicator: Bool = false
    ) {
        self.imageURL = imageURL
        self.name = name
        self.size = size
        self.showRing = showRing
        self.showOnlineIndicator = showOnlineIndicator
    }

    var body: some View {
        Group {
            if let imageURL {
                LazyImage(url: imageURL) { state in
                    if let image = state.image {
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                    } else {
                        initialsView
                    }
                }
            } else {
                initialsView
            }
        }
        .frame(width: size.dimension, height: size.dimension)
        .clipShape(Circle())
        .if(showRing) { view in
            view.overlay(
                Circle()
                    .strokeBorder(
                        RFColors.brandGradient,
                        lineWidth: 2
                    )
                    .frame(
                        width: size.dimension + 6,
                        height: size.dimension + 6
                    )
            )
        }
        .overlay(alignment: .bottomTrailing) {
            if showOnlineIndicator {
                Circle()
                    .fill(RFColors.success)
                    .frame(
                        width: size.onlineIndicatorSize,
                        height: size.onlineIndicatorSize
                    )
                    .overlay(
                        Circle()
                            .strokeBorder(
                                RFColors.fallbackBackground,
                                lineWidth: 2
                            )
                    )
            }
        }
    }

    private var initialsView: some View {
        ZStack {
            Circle()
                .fill(
                    LinearGradient(
                        colors: [
                            RFColors.fallbackPrimary.opacity(0.15),
                            RFColors.fallbackPrimary.opacity(0.25)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            Text(initials)
                .font(size.font)
                .fontWeight(.semibold)
                .foregroundStyle(RFColors.fallbackPrimary)
        }
    }

    private var initials: String {
        let components = name.split(separator: " ")
        let firstInitial = components.first?.prefix(1) ?? ""
        let lastInitial = components.count > 1 ? components.last?.prefix(1) ?? "" : ""
        return String(firstInitial + lastInitial).uppercased()
    }
}

#Preview {
    HStack(spacing: RFSpacing.md) {
        RFAvatar(name: "Atakan Natik", size: .small)
        RFAvatar(name: "Atakan Natik", size: .medium, showRing: true)
        RFAvatar(name: "Atakan Natik", size: .large, showRing: true, showOnlineIndicator: true)
    }
}
