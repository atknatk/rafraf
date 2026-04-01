import Foundation
import Testing
@testable import RafRaf

/// TaskStatus enum testleri — raw value, isRunning, isTerminal, displayName.
@Suite("TaskStatus Tests")
struct TaskStatusTests {

    // MARK: - Raw Values

    @Test("TaskStatus raw value'lari backend ile uyumlu olmali")
    func rawValues() {
        #expect(TaskStatus.queued.rawValue == "queued")
        #expect(TaskStatus.planning.rawValue == "planning")
        #expect(TaskStatus.implementing.rawValue == "implementing")
        #expect(TaskStatus.testing.rawValue == "testing")
        #expect(TaskStatus.reviewing.rawValue == "reviewing")
        #expect(TaskStatus.completed.rawValue == "completed")
        #expect(TaskStatus.failed.rawValue == "failed")
        #expect(TaskStatus.cancelled.rawValue == "cancelled")
    }

    @Test("TaskStatus tum case'ler 8 adet olmali")
    func allCasesCount() {
        #expect(TaskStatus.allCases.count == 8)
    }

    // MARK: - isRunning

    @Test("TaskStatus aktif durumlar icin isRunning true olmali")
    func isRunning_trueForActiveStatuses() {
        let activeStatuses: [TaskStatus] = [.queued, .planning, .implementing, .testing, .reviewing]

        for status in activeStatuses {
            #expect(status.isRunning == true, "Expected \(status.rawValue) isRunning to be true")
        }
    }

    @Test("TaskStatus terminal durumlar icin isRunning false olmali")
    func isRunning_falseForTerminalStatuses() {
        let terminalStatuses: [TaskStatus] = [.completed, .failed, .cancelled]

        for status in terminalStatuses {
            #expect(status.isRunning == false, "Expected \(status.rawValue) isRunning to be false")
        }
    }

    // MARK: - isTerminal

    @Test("TaskStatus terminal durumlar icin isTerminal true olmali")
    func isTerminal_trueForTerminalStatuses() {
        #expect(TaskStatus.completed.isTerminal == true)
        #expect(TaskStatus.failed.isTerminal == true)
        #expect(TaskStatus.cancelled.isTerminal == true)
    }

    @Test("TaskStatus aktif durumlar icin isTerminal false olmali")
    func isTerminal_falseForActiveStatuses() {
        let activeStatuses: [TaskStatus] = [.queued, .planning, .implementing, .testing, .reviewing]

        for status in activeStatuses {
            #expect(status.isTerminal == false, "Expected \(status.rawValue) isTerminal to be false")
        }
    }

    // MARK: - displayName

    @Test("TaskStatus her durum icin displayName bos olmamali")
    func displayName_notEmpty() {
        for status in TaskStatus.allCases {
            #expect(!status.displayName.isEmpty, "Expected \(status.rawValue) displayName to be non-empty")
        }
    }

    @Test("TaskStatus displayName localizable string donmeli")
    func displayName_returnsLocalizedString() {
        // Her status icin displayName farkli olmali
        let displayNames = Set(TaskStatus.allCases.map(\.displayName))
        #expect(displayNames.count == TaskStatus.allCases.count, "Each status should have a unique displayName")
    }

    // MARK: - Codable

    @Test("TaskStatus JSON decode dogru calismali")
    func jsonDecode() throws {
        let json = "\"implementing\""
        let data = Data(json.utf8)
        let decoded = try JSONDecoder().decode(TaskStatus.self, from: data)
        #expect(decoded == .implementing)
    }

    @Test("TaskStatus JSON encode dogru calismali")
    func jsonEncode() throws {
        let encoded = try JSONEncoder().encode(TaskStatus.reviewing)
        let json = String(data: encoded, encoding: .utf8)
        #expect(json == "\"reviewing\"")
    }
}
