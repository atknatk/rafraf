/// Monitoring dashboard data repository protocol.
protocol MonitoringRepositoryProtocol: Sendable {
    func getDashboard() async throws -> MonitoringDashboard
}
