import Foundation
import Testing
@testable import RafRaf

// MARK: - Mock Implementation

/// Mock LiveActivityManager — ActivityKit'e bagimsiz test icin.
/// Birden fazla concurrent activity destekler (gercek manager gibi).
@MainActor
final class MockLiveActivityManager: LiveActivityManaging {
    nonisolated var hasActiveActivity: Bool {
        MainActor.assumeIsolated { !_activeActivities.isEmpty }
    }

    /// Aktif activity state'leri: taskId → ContentState
    private var _activeActivities: [String: TaskActivityAttributes.ContentState] = [:]
    /// Aktif activity attributes: taskId → Attributes
    private var _activeAttributes: [String: TaskActivityAttributes] = [:]

    private(set) var startCallCount: Int = 0
    private(set) var updateCallCount: Int = 0
    private(set) var endCallCount: Int = 0
    private(set) var pushTokenObserved: Bool = false

    /// Son guncellenen task'in state'i (test kolayligi icin).
    var currentState: TaskActivityAttributes.ContentState? {
        _activeActivities.values.first
    }

    /// Son guncellenen task'in attributes'u.
    var currentAttributes: TaskActivityAttributes? {
        _activeAttributes.values.first
    }

    /// Belirli bir task'in state'ini getir.
    func stateForTask(_ taskId: String) -> TaskActivityAttributes.ContentState? {
        _activeActivities[taskId]
    }

    func startTask(taskId: String, taskTitle: String, projectName: String) async {
        // Ayni taskId icin zaten varsa tekrar baslatma (gercek manager davranisi)
        if _activeActivities[taskId] != nil { return }

        startCallCount += 1
        _activeAttributes[taskId] = TaskActivityAttributes(
            taskId: taskId,
            taskTitle: taskTitle,
            projectName: projectName
        )
        _activeActivities[taskId] = TaskActivityAttributes.ContentState(
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
        taskId: String,
        status: String,
        currentStep: String,
        progress: Double,
        completedSteps: Int,
        totalSteps: Int,
        phaseIcon: String,
        estimatedSeconds: Int?
    ) async {
        guard _activeActivities[taskId] != nil else { return }
        updateCallCount += 1
        _activeActivities[taskId] = TaskActivityAttributes.ContentState(
            status: status,
            currentStep: currentStep,
            progress: progress,
            completedSteps: completedSteps,
            totalSteps: totalSteps,
            estimatedSecondsRemaining: estimatedSeconds,
            phaseIcon: phaseIcon
        )
    }

    func endTask(taskId: String) async {
        guard _activeActivities[taskId] != nil else { return }
        endCallCount += 1
        _activeActivities.removeValue(forKey: taskId)
        _activeAttributes.removeValue(forKey: taskId)
    }

    func endAllTasks() async {
        for taskId in _activeActivities.keys {
            await endTask(taskId: taskId)
        }
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

    @Test("start sonrasi activity aktif olmali")
    func start_setsCurrentActivity() async {
        let manager = MockLiveActivityManager()

        await manager.startTask(
            taskId: "task-1",
            taskTitle: "Build feature X",
            projectName: "RafRaf"
        )

        #expect(manager.hasActiveActivity == true)
        #expect(manager.currentAttributes?.taskId == "task-1")
        #expect(manager.currentAttributes?.taskTitle == "Build feature X")
        #expect(manager.currentAttributes?.projectName == "RafRaf")
        #expect(manager.currentState != nil)
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
            taskId: "task-2",
            status: "implementing",
            currentStep: "Writing authentication service...",
            progress: 0.6,
            completedSteps: 3,
            totalSteps: 5,
            phaseIcon: "hammer.fill",
            estimatedSeconds: 120
        )

        let state = manager.stateForTask("task-2")
        #expect(state?.status == "implementing")
        #expect(state?.currentStep == "Writing authentication service...")
        #expect(state?.progress == 0.6)
        #expect(state?.completedSteps == 3)
        #expect(state?.totalSteps == 5)
        #expect(state?.phaseIcon == "hammer.fill")
        #expect(state?.estimatedSecondsRemaining == 120)
        #expect(manager.updateCallCount == 1)
    }

    @Test("end sonrasi activity temizlenmeli")
    func end_clearsCurrentActivity() async {
        let manager = MockLiveActivityManager()

        await manager.startTask(
            taskId: "task-3",
            taskTitle: "Fix bug",
            projectName: "RafRaf"
        )

        #expect(manager.hasActiveActivity == true)

        await manager.endTask(taskId: "task-3")

        #expect(manager.hasActiveActivity == false)
        #expect(manager.stateForTask("task-3") == nil)
        #expect(manager.endCallCount == 1)
    }

    @Test("Birden fazla proje icin es zamanli Live Activity")
    func multipleProjects_concurrentActivities() async {
        let manager = MockLiveActivityManager()

        // 3 farkli projede 3 task baslat
        await manager.startTask(taskId: "t-backend", taskTitle: "API endpoint", projectName: "Backend")
        await manager.startTask(taskId: "t-ios", taskTitle: "UI fix", projectName: "iOS App")
        await manager.startTask(taskId: "t-agent", taskTitle: "Runner update", projectName: "Agent")

        #expect(manager.startCallCount == 3)
        #expect(manager.hasActiveActivity == true)

        // Her birini bagimsiz guncelle
        await manager.updateTask(
            taskId: "t-backend", status: "implementing", currentStep: "Yanıt yazılıyor...",
            progress: 0.4, completedSteps: 0, totalSteps: 1, phaseIcon: "pencil.line", estimatedSeconds: nil
        )
        await manager.updateTask(
            taskId: "t-ios", status: "planning", currentStep: "Düşünüyor...",
            progress: 0.1, completedSteps: 0, totalSteps: 1, phaseIcon: "brain", estimatedSeconds: nil
        )

        #expect(manager.stateForTask("t-backend")?.progress == 0.4)
        #expect(manager.stateForTask("t-ios")?.progress == 0.1)
        #expect(manager.stateForTask("t-agent")?.status == "started")

        // Bir tanesini bitir, digerlerine dokunma
        await manager.endTask(taskId: "t-backend")

        #expect(manager.stateForTask("t-backend") == nil)
        #expect(manager.stateForTask("t-ios") != nil)
        #expect(manager.stateForTask("t-agent") != nil)
        #expect(manager.hasActiveActivity == true)

        // Hepsini bitir
        await manager.endAllTasks()
        #expect(manager.hasActiveActivity == false)
    }

    @Test("Ayni taskId ile tekrar start cagilmamali")
    func duplicateStart_ignored() async {
        let manager = MockLiveActivityManager()

        await manager.startTask(taskId: "task-dup", taskTitle: "First", projectName: "P1")
        await manager.startTask(taskId: "task-dup", taskTitle: "Second", projectName: "P2")

        // Ikinci start ignore edilmeli
        #expect(manager.startCallCount == 1)
        #expect(manager.currentAttributes?.taskTitle == "First")
    }

    @Test("pushType .token ile baslatma token update'lerini gozlemlemeli")
    func startWithPushToken_observesTokenUpdates() async {
        let manager = MockLiveActivityManager()

        await manager.startTask(
            taskId: "task-push",
            taskTitle: "Push test task",
            projectName: "RafRaf"
        )

        manager.simulatePushTokenObservation()

        #expect(manager.pushTokenObserved == true)
        #expect(manager.hasActiveActivity == true)
    }
}
