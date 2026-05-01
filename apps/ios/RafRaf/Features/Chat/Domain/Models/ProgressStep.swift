import Foundation

/// AI islem adimi domain modeli.
/// Backend'den gelen progress event'lerindeki her bir adimi temsil eder.
struct ProgressStep: Identifiable, Sendable, Equatable {
    /// Benzersiz adim ID'si.
    let id: String
    /// Adim tipi (thinking, tool_calling, generating, waiting_approval).
    let type: ProgressStepType
    /// Adim aciklamasi.
    let label: String
    /// Adim durumu.
    let status: ProgressStepStatus
    /// Adim suresi (tamamlanmissa, saniye cinsinden).
    let durationSeconds: Double?
    /// Ek detay bilgisi.
    let detail: String?
    /// Tool adi (tool_calling tipindeki adimlar icin, ornegin "Read", "Bash", "Edit").
    let toolName: String?

    init(
        id: String = UUID().uuidString,
        type: ProgressStepType,
        label: String,
        status: ProgressStepStatus = .pending,
        durationSeconds: Double? = nil,
        detail: String? = nil,
        toolName: String? = nil
    ) {
        self.id = id
        self.type = type
        self.label = label
        self.status = status
        self.durationSeconds = durationSeconds
        self.detail = detail
        self.toolName = toolName
    }
}

/// Ilerleme adimi tipleri.
/// Backend'den gelen step_type field'ina karsilik gelir.
enum ProgressStepType: String, Sendable, Equatable, CaseIterable {
    case thinking
    case toolCalling = "tool_calling"
    case generating
    case waitingApproval = "waiting_approval"
}

/// Ilerleme adimi durumlari.
enum ProgressStepStatus: String, Sendable, Equatable, CaseIterable {
    case pending
    case active
    case completed
    case failed
}
