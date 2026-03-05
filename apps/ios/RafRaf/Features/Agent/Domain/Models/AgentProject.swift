import Foundation

/// Agent ile proje arasindaki iliski domain modeli.
/// Ayni proje birden fazla agent'ta olabilir.
struct AgentProject: Identifiable, Sendable, Equatable {
    /// Composite key: "agentId:projectId"
    var id: String { "\(agentId):\(projectId)" }

    let agentId: String
    let projectId: String
    let projectName: String
    let isActive: Bool
    let repositoryUrl: String?
    let techStack: [String]
}
