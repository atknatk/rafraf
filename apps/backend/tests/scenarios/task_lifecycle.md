# Task Lifecycle Scenarios — Sprint 1

Acceptance criteria for the backend Task Persistence & State Machine feature.

---

## Scenario 1: Full task lifecycle

```
Given a user creates a task with prompt "Add voice input feature"
  And the task is persisted with status "queued"
  And progress_pct is 0 and completed_steps is 0

When the task is started
Then status should be "planning"
  And current_step should be "architect"
  And started_at should not be null

When architect completes and developer starts
Then status should be "implementing"
  And current_step should be "developer"
  And completed_steps should be 1
  And progress_pct should be 25

When developer completes and tester starts
Then status should be "testing"
  And current_step should be "tester"
  And completed_steps should be 2
  And progress_pct should be 50

When tester completes and reviewer starts
Then status should be "reviewing"
  And current_step should be "reviewer"
  And completed_steps should be 3
  And progress_pct should be 75

When reviewer approves
Then status should be "completed"
  And completed_at should not be null
  And progress_pct should be 100
  And result_summary should contain the approval summary
```

---

## Scenario 2: Task failure mid-pipeline

```
Given a running task at "implementing" step
  And current_step is "developer"
  And progress_pct is 35

When the developer agent reports an error "Compilation failed: missing module XYZ"
Then status should be "failed"
  And error_message should be "Compilation failed: missing module XYZ"
  And completed_at should not be null
  And a WebSocket "task_status" message should be broadcast with status "failed"
  And if live_activity_push_token is set, an APNs push notification should be sent
```

---

## Scenario 3: Task cancellation

```
Given a running task at "testing" step
  And current_step is "tester"
  And status is "testing"

When the user sends POST /api/v1/tasks/{id}/cancel
Then status should be "cancelled"
  And the active agent should receive a cancel signal
  And a WebSocket "task_status" message should be broadcast with status "cancelled"

---

Given a task with status "completed"
When the user sends POST /api/v1/tasks/{id}/cancel
Then the response status code should be 409
  And the error message should indicate the task cannot be cancelled
  And the task status should remain "completed"
```

---

## Scenario 4: Reconnect state recovery

```
Given a user has 2 active tasks:
  - Task A: status "implementing", progress_pct 40, current_step "developer"
  - Task B: status "queued", progress_pct 0
  And the user also has 1 completed task (Task C)

When the user reconnects via WebSocket
  And calls GET /api/v1/tasks/active
Then the response should contain exactly 2 tasks (A and B)
  And Task A should have status "implementing" with progress_pct 40
  And Task B should have status "queued" with progress_pct 0
  And Task C (completed) should NOT be in the response

When the user calls GET /api/v1/tasks/history?page=1&size=20
Then Task C should appear in the history response
  And the response should include pagination metadata (total, page, page_size)
```

---

## State Transition Rules (Reference)

Valid transitions:

| From           | Allowed To                              |
|----------------|----------------------------------------|
| QUEUED         | PLANNING                               |
| PLANNING       | IMPLEMENTING, FAILED, CANCELLED        |
| IMPLEMENTING   | TESTING, FAILED, CANCELLED             |
| TESTING        | REVIEWING, FAILED, CANCELLED           |
| REVIEWING      | COMPLETED, FAILED, CANCELLED           |
| COMPLETED      | (terminal — no transitions)            |
| FAILED         | (terminal — no transitions)            |
| CANCELLED      | (terminal — no transitions)            |

Any transition not listed above should be rejected with a `ValueError`.
