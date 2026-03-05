import Foundation

/// Calisan tek bir claude process domain modeli.
struct ClaudeProcess: Identifiable, Sendable, Equatable {
    var id: Int { pid }

    let pid: Int
    let cpuPercent: Double
    let memoryMb: Double
    let startedAt: Date?
    let cmdline: String?
}
