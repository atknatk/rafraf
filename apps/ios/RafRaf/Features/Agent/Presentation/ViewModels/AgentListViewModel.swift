import Foundation
import os

/// Agent listesi ViewModel.
/// Agent listesinin durumunu ve islemlerini yonetir.
/// Filtreleme, pull-to-refresh ve 30s otomatik yenileme destegi.
@Observable
@MainActor
final class AgentListViewModel {
    // MARK: - State

    var agents: [Agent] = []
    var isLoading: Bool = false
    var errorMessage: String?
    var selectedFilter: AgentStatus?
    var onlineCount: Int = 0
    var lastRefreshedAt: Date?

    // MARK: - Private

    private let getAgentsUseCase: GetAgentsUseCase
    private var autoRefreshTask: Task<Void, Never>?
    private let autoRefreshInterval: UInt64 = 30_000_000_000 // 30 seconds
    let getSubscriptionUsageUseCase: GetSubscriptionUsageUseCase
    let refreshSubscriptionUsageUseCase: RefreshSubscriptionUsageUseCase
    let getAgentProjectsUseCase: GetAgentProjectsUseCase
    let setProjectActiveUseCase: SetProjectActiveUseCase
    let getClaudeProcessesUseCase: GetClaudeProcessesUseCase
    let getAgentTasksUseCase: GetAgentTasksUseCase
    let cancelAgentTaskUseCase: CancelAgentTaskUseCase
    private let logger = AppLogger.logger(for: "AgentList")

    // MARK: - Init

    init(
        getAgentsUseCase: GetAgentsUseCase,
        getSubscriptionUsageUseCase: GetSubscriptionUsageUseCase,
        refreshSubscriptionUsageUseCase: RefreshSubscriptionUsageUseCase,
        getAgentProjectsUseCase: GetAgentProjectsUseCase,
        setProjectActiveUseCase: SetProjectActiveUseCase,
        getClaudeProcessesUseCase: GetClaudeProcessesUseCase,
        getAgentTasksUseCase: GetAgentTasksUseCase,
        cancelAgentTaskUseCase: CancelAgentTaskUseCase
    ) {
        self.getAgentsUseCase = getAgentsUseCase
        self.getSubscriptionUsageUseCase = getSubscriptionUsageUseCase
        self.refreshSubscriptionUsageUseCase = refreshSubscriptionUsageUseCase
        self.getAgentProjectsUseCase = getAgentProjectsUseCase
        self.setProjectActiveUseCase = setProjectActiveUseCase
        self.getClaudeProcessesUseCase = getClaudeProcessesUseCase
        self.getAgentTasksUseCase = getAgentTasksUseCase
        self.cancelAgentTaskUseCase = cancelAgentTaskUseCase
        logger.info("AgentListViewModel baslatildi")
    }

    // MARK: - Actions

    /// Agent'lari yukler ve otomatik yenilemeyi baslatir.
    func loadAgents() async {
        guard !isLoading else { return }

        isLoading = true
        errorMessage = nil

        do {
            let result = try await getAgentsUseCase.execute(status: selectedFilter)
            agents = result.agents
            onlineCount = result.onlineCount
            lastRefreshedAt = Date()
            logger.info("Agent'lar yuklendi: \(result.agents.count) agent, online: \(result.onlineCount)")
        } catch {
            errorMessage = String(localized: "agent.error.loadFailed")
            logger.error("Agent yukleme hatasi: \(error.localizedDescription)")
        }

        isLoading = false
    }

    /// 30 saniyede bir otomatik yenileme baslatir.
    func startAutoRefresh() {
        autoRefreshTask?.cancel()
        autoRefreshTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: self?.autoRefreshInterval ?? 30_000_000_000)
                guard !Task.isCancelled else { break }
                await self?.refreshAgents()
            }
        }
    }

    /// Otomatik yenilemeyi durdurur.
    func stopAutoRefresh() {
        autoRefreshTask?.cancel()
        autoRefreshTask = nil
    }

    /// Pull-to-refresh ile agent'lari yeniden yukler.
    func refreshAgents() async {
        do {
            let result = try await getAgentsUseCase.execute(status: selectedFilter)
            agents = result.agents
            onlineCount = result.onlineCount
            lastRefreshedAt = Date()
            logger.info("Agent'lar yenilendi: \(result.agents.count) agent")
        } catch {
            errorMessage = String(localized: "agent.error.refreshFailed")
            logger.error("Agent yenileme hatasi: \(error.localizedDescription)")
        }
    }

    /// Durum filtresini degistirir ve agent'lari yeniden yukler.
    func filterByStatus(_ status: AgentStatus?) async {
        selectedFilter = status
        await loadAgents()
    }

    /// Hata mesajini temizler.
    func dismissError() {
        errorMessage = nil
    }
}
