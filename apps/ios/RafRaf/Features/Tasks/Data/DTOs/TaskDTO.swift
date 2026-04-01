import Foundation

/// Task olusturma istegi icin DTO.
struct CreateTaskRequestDTO: Codable, Sendable {
    let title: String
    let prompt: String
    let taskType: String
    let projectId: UUID?

    enum CodingKeys: String, CodingKey {
        case title
        case prompt
        case taskType = "task_type"
        case projectId = "project_id"
    }
}

/// Live Activity token kaydi icin DTO.
struct LiveActivityTokenDTO: Codable, Sendable {
    let pushToken: String

    enum CodingKeys: String, CodingKey {
        case pushToken = "push_token"
    }
}
