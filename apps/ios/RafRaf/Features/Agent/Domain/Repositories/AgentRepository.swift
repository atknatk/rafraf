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

    /// Agent gorev gecmisini getirir.
    func getAgentTasks(agentId: String, limit: Int) async throws -> AgentTaskListResult

    /// Bir gorevi iptal eder.
    func cancelAgentTask(agentId: String, taskId: String) async throws

    /// Agent'a yeni bir gorev gonderir.
    func dispatchTask(agentId: String, runner: String, action: String, params: [String: String]) async throws

    /// Agent'in proje dizinlerini yeniden tarar.
    func rescanProjects(agentId: String) async throws
}
