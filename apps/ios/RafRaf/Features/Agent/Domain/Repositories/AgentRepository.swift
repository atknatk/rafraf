import Foundation

/// Agent repository protokolu.
/// Domain katmani Data katmanindan izole kalir; bu protokol uzerinden iletisir.
protocol AgentRepositoryProtocol: Sendable {
    /// Agent listesini getirir.
    /// - Parameter status: Opsiyonel durum filtresi
    /// - Returns: Agent listesi sonucu
    func getAgents(status: AgentStatus?) async throws -> AgentListResult
}
