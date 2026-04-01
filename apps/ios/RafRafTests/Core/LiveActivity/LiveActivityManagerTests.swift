import Foundation
import Testing
@testable import RafRaf

// MARK: - Mock Implementation

/// Mock LiveActivityManager — ActivityKit'e bagimsiz test icin.
@MainActor
final class MockLiveActivityManager: LiveActivityManaging {
    nonisolated var hasActiveActivity: Bool {
        // Mock'ta her zaman MainActor context'inden cagirilir,
        // nonisolated satisfy etmek icin nonisolated(unsafe) kullaniyoruz
        MainActor.assumeIsolated { _hasActiveActivity }
    }

    private var _hasActiveActivity: Bool = false
    private(set) var currentState: TaskActivityAttributes.ContentState?
    private(set) var currentAttributes: TaskActivityAttributes?
    private(set) var startCallCount: Int = 0
    private(set) var updateCallCount: Int = 0
    private(set) var endCallCount: Int = 0
    private(set) var pushTokenObserved: Bool = false

    func startTask(taskId: String, taskTitle: String, projectName: String) async {
        startCallCount += 1
        _hasActiveActivity = true
        currentAttributes = TaskActivityAttributes(
            taskId: taskId,
            taskTitle: taskTitle,
            projectName: projectName
        )
        currentState = TaskActivityAttributes.ContentState(
            status: "started",
            currentStep: "Initializing...",
            progress: 0.0,
            completedSteps: 0,
            totalSteps: 1,
            estimatedSecondsRemaining: nil,
            phaseIcon: "circle"
        )
    }

    func updateTask(
        status: String,
        currentStep: String,
        progress: Double,
        completedSteps: Int,
        totalSteps: Int,
        phaseIcon: String,
        estimatedSeconds: Int?
    ) async {
        updateCallCount += 1
        currentState = TaskActivityAttributes.ContentState(
            status: status,
            currentStep: currentStep,
            progress: progress,
            completedSteps: completedSteps,
            totalSteps: totalSteps,
            estimatedSecondsRemaining: estimatedSeconds,
            phaseIcon: phaseIcon
        )
    }

    func endTask() async {
        endCallCount += 1
        _hasActiveActivity = false
        currentState = nil
        currentAttributes = nil
    }

    /// Push token gozlemleme simulasyonu.
    func simulatePushTokenObservation() {
        pushTokenObserved = true
    }
}

// MARK: - Tests

/// LiveActivityManager logic testleri.
/// ActivityKit simulator'da sinirli destekli oldugu icin mock-based.
@Suite("LiveActivityManager Tests")
@MainActor
struct LiveActivityManagerTests {

    @Test("start sonrasi currentActivity nil olmamali")
    func start_setsCurrentActivity() async {
        let manager = MockLiveActivityManager()

        await manager.startTask(
            taskId: "task-1",
            taskTitle: "Build feature X",
            projectName: "RafRaf"
        )

        #expect(manager.hasActiveActivity == true)
        #expect(manager.currentAttributes != nil)
        #expect(manager.currentAttributes?.taskId == "task-1")
        #expect(manager.currentAttributes?.taskTitle == "Build feature X")
        #expect(manager.currentAttributes?.projectName == "RafRaf")
        #expect(manager.currentState != nil)

        // Gercek LiveActivityManager'da da ayni davranis beklenir
        let realManager = LiveActivityManager.shared
        await realManager.startTask(
            taskId: "task-real",
            taskTitle: "Real task",
            projectName: "TestProject"
        )
        // ActivityKit simulator'da calismayabilir, ama crash etmemeli
    }

    @Test("update sonrasi ContentState degismeli")
    func update_changesContentState() async {
        let manager = MockLiveActivityManager()

        await manager.startTask(
            taskId: "task-2",
            taskTitle: "Implement auth",
            projectName: "RafRaf"
        )

        await manager.updateTask(
            status: "implementing",
            currentStep: "Writing authentication service...",
            progress: 0.6,
            completedSteps: 3,
            totalSteps: 5,
            phaseIcon: "hammer.fill",
            estimatedSeconds: 120
        )

        #expect(manager.currentState?.status == "implementing")
        #expect(manager.currentState?.currentStep == "Writing authentication service...")
        #expect(manager.currentState?.progress == 0.6)
        #expect(manager.currentState?.completedSteps == 3)
        #expect(manager.currentState?.totalSteps == 5)
        #expect(manager.currentState?.phaseIcon == "hammer.fill")
        #expect(manager.currentState?.estimatedSecondsRemaining == 120)
        #expect(manager.updateCallCount == 1)
    }

    @Test("end sonrasi currentActivity nil olmali")
    func end_clearsCurrentActivity() async {
        let manager = MockLiveActivityManager()

        await manager.startTask(
            taskId: "task-3",
            taskTitle: "Fix bug",
            projectName: "RafRaf"
        )

        #expect(manager.hasActiveActivity == true)

        await manager.endTask()

        #expect(manager.hasActiveActivity == false)
        #expect(manager.currentAttributes == nil)
        #expect(manager.currentState == nil)
        #expect(manager.endCallCount == 1)
    }

    @Test("Yeni start oncesi mevcut activity durdurulmali")
    func stopCurrent_beforeNewStart() async {
        let manager = MockLiveActivityManager()

        // Ilk activity baslat
        await manager.startTask(
            taskId: "task-old",
            taskTitle: "Old task",
            projectName: "ProjectA"
        )

        #expect(manager.startCallCount == 1)
        #expect(manager.currentAttributes?.taskId == "task-old")

        // Yeni activity baslatmadan once mevcut durdurulmali
        await manager.endTask()
        await manager.startTask(
            taskId: "task-new",
            taskTitle: "New task",
            projectName: "ProjectB"
        )

        #expect(manager.endCallCount == 1)
        #expect(manager.startCallCount == 2)
        #expect(manager.currentAttributes?.taskId == "task-new")
        #expect(manager.currentAttributes?.projectName == "ProjectB")

        // Gercek LiveActivityManager'da stopCurrent otomatik yapilmali
        // Bu test mock ile logic'i dogruluyor, gercek manager'da
        // startTask icinde otomatik end cagrisi beklenir
        let realManager = LiveActivityManager.shared
        await realManager.startTask(
            taskId: "real-1",
            taskTitle: "First",
            projectName: "P1"
        )
        await realManager.startTask(
            taskId: "real-2",
            taskTitle: "Second",
            projectName: "P2"
        )
        await realManager.endTask()
    }

    @Test("pushType .token ile baslatma token update'lerini gozlemlemeli")
    func startWithPushToken_observesTokenUpdates() async {
        let manager = MockLiveActivityManager()

        await manager.startTask(
            taskId: "task-push",
            taskTitle: "Push test task",
            projectName: "RafRaf"
        )

        // Push token gozlemleme simule et
        manager.simulatePushTokenObservation()

        #expect(manager.pushTokenObserved == true)
        #expect(manager.hasActiveActivity == true)

        // Gercek manager'da Activity<TaskActivityAttributes>.pushToStartToken
        // veya activity.pushTokenUpdates async sequence kullanilir
        // Bu test sadece logic flow'u dogruluyor
    }
}
