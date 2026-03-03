import Foundation
import Testing
@testable import RafRaf

/// HandleNotificationUseCase testleri.
@Suite("HandleNotificationUseCase Tests")
struct HandleNotificationUseCaseTests {
    let useCase = HandleNotificationUseCase()

    @Test("Gecerli payload ile PushNotification donmeli")
    func validPayload() {
        let userInfo: [String: Any] = [
            "aps": [
                "alert": [
                    "title": "Gorev Tamamlandi",
                    "body": "Proje X deploy edildi."
                ],
                "badge": 3
            ],
            "notification_type": "task_complete",
            "notification_id": "550e8400-e29b-41d4-a716-446655440000",
            "deep_link": "rafraf://chat/session-123"
        ]

        let result = useCase.execute(userInfo: userInfo)

        #expect(result != nil)
        #expect(result?.title == "Gorev Tamamlandi")
        #expect(result?.body == "Proje X deploy edildi.")
        #expect(result?.category == .taskComplete)
        #expect(result?.badgeCount == 3)
        #expect(result?.deepLink == "rafraf://chat/session-123")
    }

    @Test("Gecersiz payload nil donmeli (aps yok)")
    func missingAps() {
        let userInfo: [String: Any] = [
            "notification_type": "info"
        ]

        let result = useCase.execute(userInfo: userInfo)
        #expect(result == nil)
    }

    @Test("Bilinmeyen notification_type info'ya dusmeli")
    func unknownNotificationType() {
        let userInfo: [String: Any] = [
            "aps": [
                "alert": [
                    "title": "Test",
                    "body": "Test body"
                ]
            ],
            "notification_type": "unknown_type"
        ]

        let result = useCase.execute(userInfo: userInfo)

        #expect(result != nil)
        #expect(result?.category == .info)
    }

    @Test("notification_type olmadanda info olmali")
    func missingNotificationType() {
        let userInfo: [String: Any] = [
            "aps": [
                "alert": [
                    "title": "Test",
                    "body": "Msg"
                ]
            ]
        ]

        let result = useCase.execute(userInfo: userInfo)

        #expect(result != nil)
        #expect(result?.category == .info)
    }

    @Test("Badge yoksa 0 olmali")
    func missingBadge() {
        let userInfo: [String: Any] = [
            "aps": [
                "alert": [
                    "title": "Test",
                    "body": "Msg"
                ]
            ]
        ]

        let result = useCase.execute(userInfo: userInfo)

        #expect(result != nil)
        #expect(result?.badgeCount == 0)
    }

    @Test("Deep link opsiyonel olmali")
    func noDeepLink() {
        let userInfo: [String: Any] = [
            "aps": [
                "alert": [
                    "title": "Test",
                    "body": "Msg"
                ]
            ]
        ]

        let result = useCase.execute(userInfo: userInfo)

        #expect(result != nil)
        #expect(result?.deepLink == nil)
    }

    @Test("approval_needed tipi dogru parse edilmeli")
    func approvalNeededType() {
        let userInfo: [String: Any] = [
            "aps": [
                "alert": [
                    "title": "Onay",
                    "body": "Onay gerekiyor"
                ]
            ],
            "notification_type": "approval_needed"
        ]

        let result = useCase.execute(userInfo: userInfo)

        #expect(result != nil)
        #expect(result?.category == .approvalNeeded)
    }
}
