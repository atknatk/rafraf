import Foundation
import os

/// Agent listesi ViewModel.
/// Agent listesinin durumunu ve islemlerini yonetir.
/// Filtreleme ve pull-to-refresh destegi.
@Observable
@MainActor
final class AgentListViewModel {
    // MARK: - State

    var agents: [Agent] = []
    var isLoading: Bool = false
    var errorMessage: String?
    var selectedFilter: AgentStatus?
    var onlineCount: Int = 0

    // MARK: - Private

    private let getAgentsUseCase: GetAgentsUseCase
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

    /// Agent'lari yukler.
    func loadAgents() async {
        guard !isLoading else { return }

        isLoading = true
        errorMessage = nil

        do {
            let result = try await getAgentsUseCase.execute(status: selectedFilter)
            agents = result.agents
            onlineCount = result.onlineCount
            logger.info("Agent'lar yuklendi: \(result.agents.count) agent, online: \(result.onlineCount)")
        } catch {
            errorMessage = String(localized: "agent.error.loadFailed")
            logger.error("Agent yukleme hatasi: \(error.localizedDescription)")
        }

        isLoading = false
    }

    /// Pull-to-refresh ile agent'lari yeniden yukler.
    func refreshAgents() async {
        do {
            let result = try await getAgentsUseCase.execute(status: selectedFilter)
            agents = result.agents
            onlineCount = result.onlineCount
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
