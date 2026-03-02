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
}

/// RafRaf avatar bileseni.
/// Kullanici profil resmi veya bos harf gostergesi.
struct RFAvatar: View {
    let imageURL: URL?
    let name: String
    let size: RFAvatarSize

    init(
        imageURL: URL? = nil,
        name: String,
        size: RFAvatarSize = .medium
    ) {
        self.imageURL = imageURL
        self.name = name
        self.size = size
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
    }

    private var initialsView: some View {
        ZStack {
            Circle()
                .fill(RFColors.fallbackPrimary.opacity(0.2))

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
        RFAvatar(name: "Atakan Natik", size: .medium)
        RFAvatar(name: "Atakan Natik", size: .large)
    }
}
