import Foundation

/// Backend'den gelen progress event DTO'su.
/// `shared/api-contracts/ws/websocket-messages.json` progress content'ine uygun.
struct ProgressEventDTO: Codable, Sendable {
    let task: String
    let step: Int
    let totalSteps: Int
    let percentage: Int
    let details: String?
}

/// Backend'den gelen detayli progress event DTO'su.
/// Asamali ilerleme icin step bilgilerini icerir.
struct ProgressStepDTO: Codable, Sendable {
    let id: String
    let type: String
    let label: String
    let status: String
    let durationSeconds: Double?
    let detail: String?
}

/// Backend'den gelen tam progress state DTO'su.
struct ProgressStateDTO: Codable, Sendable {
    let id: String
    let mode: String?
    let percentage: Int
    let taskDescription: String
    let steps: [ProgressStepDTO]?
    let currentStepIndex: Int?
    let status: String?
}
