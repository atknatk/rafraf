import Foundation

/// Proje domain modeli.
/// Kullanicinin olusturup yonettigi projeleri temsil eder.
struct Project: Identifiable, Sendable, Equatable {
    let id: String
    let name: String
    let description: String
    let createdAt: Date
    let updatedAt: Date
    let status: ProjectStatus
}

/// Proje durumlari.
enum ProjectStatus: String, Sendable, Equatable {
    case active
    case archived
    case completed
}
