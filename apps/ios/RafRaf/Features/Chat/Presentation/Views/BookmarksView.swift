import SwiftUI

/// Kaydedilmis mesajlar ekrani.
struct BookmarksView: View {
    @Environment(\.dismiss) private var dismiss
    let bookmarkService: BookmarkService

    var body: some View {
        NavigationStack {
            Group {
                if bookmarkService.bookmarks.isEmpty {
                    RFEmptyStateView(
                        systemImage: "bookmark",
                        title: String(localized: "bookmarks.empty.title"),
                        message: String(localized: "bookmarks.empty.message")
                    )
                } else {
                    List {
                        ForEach(bookmarkService.bookmarks) { bm in
                            BookmarkRow(bookmark: bm) {
                                bookmarkService.removeBookmark(id: bm.id)
                            }
                            .listRowBackground(RFColors.fallbackSurface)
                        }
                        .onDelete { indexSet in
                            for index in indexSet {
                                let bm = bookmarkService.bookmarks[index]
                                bookmarkService.removeBookmark(id: bm.id)
                            }
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle(String(localized: "bookmarks.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(String(localized: "common.cancel")) { dismiss() }
                }
            }
        }
    }
}

private struct BookmarkRow: View {
    let bookmark: BookmarkedMessage
    let onRemove: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xs) {
            HStack {
                Image(systemName: "bookmark.fill")
                    .foregroundStyle(RFColors.fallbackPrimary)
                    .font(.system(size: 12))
                if let projectName = bookmark.projectName {
                    RFText(projectName, style: .captionBold, color: RFColors.fallbackPrimary)
                }
                Spacer()
                RFText(
                    bookmark.savedAt.formatted(.relative(presentation: .named)),
                    style: .caption,
                    color: RFColors.fallbackTextTertiary
                )
            }
            RFText(bookmark.content, style: .body, color: RFColors.fallbackTextPrimary)
                .lineLimit(4)

            Button {
                UIPasteboard.general.string = bookmark.content
            } label: {
                Label(String(localized: "bookmarks.copy"), systemImage: "doc.on.doc")
                    .font(.system(size: 12))
                    .foregroundStyle(RFColors.fallbackTextSecondary)
            }
            .buttonStyle(.plain)
        }
        .padding(.vertical, RFSpacing.xs)
        .swipeActions(edge: .trailing) {
            Button(role: .destructive, action: onRemove) {
                Label(String(localized: "bookmarks.remove"), systemImage: "bookmark.slash")
            }
        }
    }
}

#Preview {
    let svc = BookmarkService()
    return BookmarksView(bookmarkService: svc)
}
