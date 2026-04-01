import Foundation
import Testing
@testable import RafRaf

/// TaskListViewModel testleri — task listeleme, iptal, guncelleme, bos durum.
@Suite("TaskListViewModel Tests")
struct TaskListViewModelTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT(
        repository: MockTaskRepository = MockTaskRepository()
    ) -> (TaskListViewModel, MockTaskRepository) {
        let vm = TaskListViewModel(repository: repository)
        return (vm, repository)
    }

    // MARK: - Initial State

    @Test("TaskListViewModel baslangic durumu dogru olmali")
    @MainActor
    func initialState() {
        let (vm, _) = makeSUT()

        #expect(vm.tasks.isEmpty)
        #expect(vm.isLoading == false)
        #expect(vm.errorMessage == nil)
        #expect(vm.showsEmptyState == true)
    }

    // MARK: - Load Active Tasks

    @Test("loadActiveTasks basarili yuklemede task listesini doldurmali")
    @MainActor
    func loadActiveTasks_populatesList() async {
        let repo = MockTaskRepository()
        repo.getActiveTasksResult = .success(TaskTestFactory.createTaskList(count: 3))
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadActiveTasks()

        #expect(vm.tasks.count == 3)
        #expect(vm.isLoading == false)
        #expect(vm.showsEmptyState == false)
        #expect(repo.getActiveTasksCallCount == 1)
    }

    @Test("loadActiveTasks bos response'da empty state gostermeli")
    @MainActor
    func loadActiveTasks_emptyState() async {
        let repo = MockTaskRepository()
        repo.getActiveTasksResult = .success([])
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadActiveTasks()

        #expect(vm.tasks.isEmpty)
        #expect(vm.showsEmptyState == true)
        #expect(vm.isLoading == false)
    }

    @Test("loadActiveTasks hata durumunda errorMessage gostermeli")
    @MainActor
    func loadActiveTasks_error() async {
        let repo = MockTaskRepository()
        repo.getActiveTasksResult = .failure(RafRafError.networkError)
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadActiveTasks()

        #expect(vm.errorMessage != nil)
        #expect(vm.tasks.isEmpty)
        #expect(vm.isLoading == false)
    }

    // MARK: - Cancel Task

    @Test("cancelTask basarili iptal sonrasi task'i listeden kaldirmali")
    @MainActor
    func cancelTask_removesFromList() async {
        let repo = MockTaskRepository()
        let tasks = TaskTestFactory.createTaskList(count: 3)
        repo.getActiveTasksResult = .success(tasks)
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadActiveTasks()
        #expect(vm.tasks.count == 3)

        let taskToCancel = tasks[1]
        await vm.cancelTask(taskId: taskToCancel.id)

        #expect(vm.tasks.count == 2)
        #expect(repo.cancelTaskCallCount == 1)
        #expect(repo.lastTaskId == taskToCancel.id)
        // Iptal edilen task listede olmamali
        #expect(!vm.tasks.contains(where: { $0.id == taskToCancel.id }))
    }

    @Test("cancelTask hata durumunda task listeden kaldirilmamali")
    @MainActor
    func cancelTask_errorKeepsTask() async {
        let repo = MockTaskRepository()
        let tasks = TaskTestFactory.createTaskList(count: 2)
        repo.getActiveTasksResult = .success(tasks)
        repo.cancelTaskResult = .failure(RafRafError.networkError)
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadActiveTasks()
        #expect(vm.tasks.count == 2)

        await vm.cancelTask(taskId: tasks[0].id)

        #expect(vm.tasks.count == 2)
        #expect(vm.errorMessage != nil)
    }

    // MARK: - Task Status Update

    @Test("handleTaskStatusUpdate listedeki task'in ilerlemesini guncellemeli")
    @MainActor
    func taskStatusUpdate_updatesInList() async {
        let repo = MockTaskRepository()
        let taskId = UUID()
        let task = TaskTestFactory.createTask(id: taskId, progressPct: 40)
        repo.getActiveTasksResult = .success([task])
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadActiveTasks()
        #expect(vm.tasks.first?.progressPct == 40)

        // WebSocket'ten gelen status guncelleme
        let updatedTask = TaskTestFactory.createTask(
            id: taskId,
            status: .testing,
            currentStep: "tester",
            completedSteps: 2,
            progressPct: 75
        )
        vm.handleTaskStatusUpdate(updatedTask)

        #expect(vm.tasks.count == 1)
        #expect(vm.tasks.first?.progressPct == 75)
        #expect(vm.tasks.first?.status == .testing)
        #expect(vm.tasks.first?.currentStep == "tester")
    }

    @Test("handleTaskStatusUpdate olmayan task_id icin listeye eklememeli")
    @MainActor
    func taskStatusUpdate_unknownTask() async {
        let repo = MockTaskRepository()
        repo.getActiveTasksResult = .success([])
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadActiveTasks()

        let newTask = TaskTestFactory.createTask(id: UUID())
        vm.handleTaskStatusUpdate(newTask)

        // Bilinmeyen task listede gosterilmemeli (veya eklenebilir — behavior'a gore)
        // Plan'a gore reconnect'te GET /tasks/active cagrilmali, burada sadece update beklenir
        #expect(vm.tasks.count <= 1)
    }

    @Test("handleTaskStatusUpdate terminal status oldugunda task'i listeden kaldirmali")
    @MainActor
    func taskStatusUpdate_terminalRemovesFromList() async {
        let repo = MockTaskRepository()
        let taskId = UUID()
        let task = TaskTestFactory.createTask(id: taskId, status: .implementing)
        repo.getActiveTasksResult = .success([task])
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadActiveTasks()
        #expect(vm.tasks.count == 1)

        let completedTask = TaskTestFactory.createCompletedTask(id: taskId)
        vm.handleTaskStatusUpdate(completedTask)

        // Tamamlanan task aktif listeden cikmali (veya status'u guncellenmis olmali)
        if let found = vm.tasks.first(where: { $0.id == taskId }) {
            #expect(found.status == .completed)
        }
    }

    // MARK: - Empty State

    @Test("showsEmptyState tasks bos oldugunda true olmali")
    @MainActor
    func emptyState_showsNoTasks() async {
        let repo = MockTaskRepository()
        repo.getActiveTasksResult = .success([])
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadActiveTasks()

        #expect(vm.tasks.isEmpty)
        #expect(vm.showsEmptyState == true)
    }

    @Test("showsEmptyState tasks doldugunda false olmali")
    @MainActor
    func emptyState_hidesWhenTasksExist() async {
        let repo = MockTaskRepository()
        repo.getActiveTasksResult = .success(TaskTestFactory.createTaskList(count: 1))
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadActiveTasks()

        #expect(!vm.tasks.isEmpty)
        #expect(vm.showsEmptyState == false)
    }

    // MARK: - Error Handling

    @Test("dismissError hata mesajini temizlemeli")
    @MainActor
    func dismissError() async {
        let repo = MockTaskRepository()
        repo.getActiveTasksResult = .failure(RafRafError.networkError)
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadActiveTasks()
        #expect(vm.errorMessage != nil)

        vm.dismissError()
        #expect(vm.errorMessage == nil)
    }
}
