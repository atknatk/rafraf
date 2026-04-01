import Foundation

/// AI tarafindan yonetilen bir gorevi temsil eden domain modeli.
struct AITask: Identifiable, Codable, Sendable, Equatable {
    let id: UUID
    let title: String
    let prompt: String
    let taskType: String
    let status: TaskStatus
    let currentStep: String?
    let totalSteps: Int
    let completedSteps: Int
    let progressPct: Int
    let resultSummary: String?
    let errorMessage: String?
    let projectName: String?
    let createdAt: Date
    let startedAt: Date?
    let completedAt: Date?

    /// Ilerleme yuzdesi 0.0 - 1.0 arasi kesirli deger.
    var progressFraction: Double {
        Double(progressPct) / 100.0
    }

    /// Adim bazli ilerleme orani (0.0 - 1.0).
    var stepProgress: Double {
        guard totalSteps > 0 else { return 0.0 }
        return Double(completedSteps) / Double(totalSteps)
    }
}
