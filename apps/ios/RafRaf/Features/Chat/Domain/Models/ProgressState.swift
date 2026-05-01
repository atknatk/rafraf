import Foundation

/// AI islem ilerleme durumu domain modeli.
/// Genel ilerleme bilgisini ve adim listesini icerir.
struct ProgressState: Identifiable, Sendable, Equatable {
    /// Benzersiz ilerleme ID'si.
    let id: String
    /// Ilerleme modu (determinate veya indeterminate).
    let mode: ProgressMode
    /// Genel ilerleme yuzdesi (0-100, sadece determinate modda anlamli).
    let percentage: Int
    /// Mevcut gorev aciklamasi.
    let taskDescription: String
    /// Adim listesi (step-by-step gosterge).
    let steps: [ProgressStep]
    /// Mevcut aktif adim indexi.
    let currentStepIndex: Int?
    /// Ilerleme durumu.
    let status: ProgressOverallStatus

    init(
        id: String = UUID().uuidString,
        mode: ProgressMode = .indeterminate,
        percentage: Int = 0,
        taskDescription: String,
        steps: [ProgressStep] = [],
        currentStepIndex: Int? = nil,
        status: ProgressOverallStatus = .running
    ) {
        self.id = id
        self.mode = mode
        self.percentage = percentage
        self.taskDescription = taskDescription
        self.steps = steps
        self.currentStepIndex = currentStepIndex
        self.status = status
    }
}

/// Ilerleme modu.
enum ProgressMode: String, Sendable, Equatable, CaseIterable {
    /// Yuzdeli ilerleme (0-100).
    case determinate
    /// Suresiz / belirsiz ilerleme.
    case indeterminate
}

/// Genel ilerleme durumu.
enum ProgressOverallStatus: String, Sendable, Equatable, CaseIterable {
    case running
    case completed
    case failed
    case cancelled
}
