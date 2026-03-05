import Foundation

/// Agent repository protokolu.
/// Domain katmani Data katmanindan izole kalir; bu protokol uzerinden iletisir.
protocol AgentRepositoryProtocol: Sendable {
    /// Agent listesini getirir.
    /// - Parameter status: Opsiyonel durum filtresi
    /// - Returns: Agent listesi sonucu
    func getAgents(status: AgentStatus?) async throws -> AgentListResult

    /// Subscription kullanim bilgilerini getirir.
    func getSubscriptionUsage() async throws -> SubscriptionUsage

    /// Subscription kullanim bilgilerini yeniler.
    func refreshSubscriptionUsage() async throws -> SubscriptionUsage

    /// Agent'a bagli projeleri getirir.
    func getAgentProjects(agentId: String) async throws -> [AgentProject]

    /// Agent'ta bir projeyi aktif/pasif yapar.
    func setProjectActive(agentId: String, projectId: String, isActive: Bool) async throws -> AgentProject

    /// Agent'taki calisan claude process listesini getirir.
    func getClaudeProcesses(agentId: String) async throws -> [ClaudeProcess]

    /// Tum agentlara bagli projeleri DB'den getirir (agent online olmak zorunda degil).
    func getAllAgentProjects() async throws -> [AgentProject]
}
