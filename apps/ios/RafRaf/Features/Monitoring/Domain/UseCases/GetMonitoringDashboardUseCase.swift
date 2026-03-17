/// Monitoring dashboard verisini cekmek icin use case.
struct GetMonitoringDashboardUseCase: Sendable {
    private let repository: MonitoringRepositoryProtocol

    init(repository: MonitoringRepositoryProtocol) {
        self.repository = repository
    }

    func execute() async throws -> MonitoringDashboard {
        try await repository.getDashboard()
    }
}
