import Foundation

/// Monitoring dashboard repository implementasyonu.
final class MonitoringRepositoryImpl: MonitoringRepositoryProtocol, @unchecked Sendable {
    private let networkClient: NetworkClient

    init(networkClient: NetworkClient) {
        self.networkClient = networkClient
    }

    func getDashboard() async throws -> MonitoringDashboard {
        let dto: MonitoringDashboardDTO = try await networkClient.get(
            path: "/monitoring/dashboard"
        )
        return MonitoringMapper.toDomain(from: dto)
    }
}
