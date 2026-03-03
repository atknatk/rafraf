import Foundation
import Testing
@testable import RafRaf

/// NotificationCategory domain model testleri.
@Suite("NotificationCategory Tests")
struct NotificationCategoryTests {

    @Test("Tum kategoriler mevcut olmali")
    func allCases() {
        let allCases = NotificationCategory.allCases
        #expect(allCases.count == 4)
        #expect(allCases.contains(.taskComplete))
        #expect(allCases.contains(.approvalNeeded))
        #expect(allCases.contains(.error))
        #expect(allCases.contains(.info))
    }

    @Test("RawValue degerleri backend ile uyumlu olmali")
    func rawValues() {
        #expect(NotificationCategory.taskComplete.rawValue == "task_complete")
        #expect(NotificationCategory.approvalNeeded.rawValue == "approval_needed")
        #expect(NotificationCategory.error.rawValue == "error")
        #expect(NotificationCategory.info.rawValue == "info")
    }

    @Test("LocalizedTitle bos olmamali")
    func localizedTitles() {
        for category in NotificationCategory.allCases {
            #expect(!category.localizedTitle.isEmpty)
        }
    }

    @Test("IconName bos olmamali")
    func iconNames() {
        for category in NotificationCategory.allCases {
            #expect(!category.iconName.isEmpty)
        }
    }

    @Test("RawValue'dan init dogru calismali")
    func initFromRawValue() {
        #expect(NotificationCategory(rawValue: "task_complete") == .taskComplete)
        #expect(NotificationCategory(rawValue: "approval_needed") == .approvalNeeded)
        #expect(NotificationCategory(rawValue: "error") == .error)
        #expect(NotificationCategory(rawValue: "info") == .info)
        #expect(NotificationCategory(rawValue: "unknown") == nil)
    }
}
