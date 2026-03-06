import Factory
import SwiftUI

/// Konusma mesajlari icinde arama ekrani.
struct ChatSearchView: View {
    let projectId: String?
    @State private var query = ""
    @State private var results: [ChatMessage] = []
    @State private var isSearching = false
    @Environment(\.dismiss) private var dismiss
    private let networkClient = Container.shared.networkClient()

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                searchResultsList
            }
            .navigationTitle(String(localized: "chat.search.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(String(localized: "common.cancel")) { dismiss() }
                }
            }
            .searchable(text: $query, prompt: String(localized: "chat.search.prompt"))
            .onChange(of: query) { _, newValue in
                if newValue.count >= 2 {
                    Task { await performSearch(query: newValue) }
                } else {
                    results = []
                }
            }
        }
    }

    @ViewBuilder
    private var searchResultsList: some View {
        if isSearching {
            ProgressView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if results.isEmpty && !query.isEmpty && query.count >= 2 {
            RFEmptyStateView(
                systemImage: "magnifyingglass",
                title: String(localized: "chat.search.noResults"),
                message: String(localized: "chat.search.noResultsMessage")
            )
        } else {
            List(results) { message in
                ChatSearchResultRow(message: message)
                    .listRowBackground(RFColors.fallbackSurface)
            }
            .listStyle(.plain)
        }
    }

    private func performSearch(query: String) async {
        isSearching = true
        defer { isSearching = false }
        do {
            var queryItems: [URLQueryItem] = [
                URLQueryItem(name: "q", value: query),
                URLQueryItem(name: "limit", value: "30")
            ]
            if let projectId {
                queryItems.append(URLQueryItem(name: "project_id", value: projectId))
            }
            let dtos: [MessageDTO] = try await networkClient.get(
                path: "/conversations/search",
                queryItems: queryItems
            )
            results = dtos.map { dto in
                ChatMessage(
                    id: dto.id,
                    content: dto.content,
                    sender: dto.role == "user" ? .user : .assistant,
                    timestamp: ISO8601DateFormatter().date(from: dto.createdAt ?? "") ?? Date()
                )
            }
        } catch {
            results = []
        }
    }
}

/// Arama sonucu satiri.
private struct ChatSearchResultRow: View {
    let message: ChatMessage

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xs) {
            HStack {
                Image(systemName: message.sender == .user ? "person.circle" : "brain")
                    .foregroundStyle(message.sender == .user ? RFColors.fallbackPrimary : RFColors.success)
                    .font(.system(size: 14))
                RFText(
                    message.sender == .user
                        ? String(localized: "chat.sender.user")
                        : String(localized: "chat.sender.assistant"),
                    style: .captionBold,
                    color: message.sender == .user ? RFColors.fallbackPrimary : RFColors.success
                )
                Spacer()
                RFText(
                    message.timestamp.formatted(.relative(presentation: .named)),
                    style: .caption,
                    color: RFColors.fallbackTextTertiary
                )
            }
            RFText(
                message.content,
                style: .body,
                color: RFColors.fallbackTextPrimary
            )
            .lineLimit(3)
        }
        .padding(.vertical, RFSpacing.xs)
    }
}

#Preview {
    ChatSearchView(projectId: nil)
}
