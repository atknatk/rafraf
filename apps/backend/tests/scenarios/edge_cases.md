# Edge Case Scenarios — Sprint 5: Integration & Edge Cases

Acceptance criteria for edge cases around agent crashes, stale Live Activities,
push token refresh, and deep linking from Live Activity.

---

## Scenario 1: Agent crashes during active task

```
Given a task with status "implementing"
  And current_step is "developer"
  And the task is assigned to agent "macbook-pro"
  And the agent's last_heartbeat was more than 90 seconds ago

When the TaskOrchestratorService runs its stale agent check (check_stale_agents)
Then the task status should transition to "failed"
  And error_message should indicate agent disconnection (e.g. "Agent heartbeat timeout")
  And completed_at should be set to the current timestamp

When the task transitions to "failed"
  And the task has a registered live_activity_push_token
Then a visible APNs push notification should be sent with:
  - title containing "Task Failed" or similar
  - body containing "agent" or "disconnected" or the error reason
  And a Live Activity "end" event should be sent to dismiss the Dynamic Island

When the task transitions to "failed"
  And the task does NOT have a live_activity_push_token
Then only a standard visible push notification should be sent (via device push token)
  And no APNs Live Activity push should be attempted
```

---

## Scenario 2: Stale Live Activity — 8 hour limit

```
Given a task with status "implementing"
  And the task started more than 8 hours ago (started_at < now - 8h)
  And a Live Activity is active for this task on the user's device
  And the Live Activity push token is still valid

When the TaskOrchestratorService runs its periodic stale activity check
Then a Live Activity "end" event should be sent via APNs to dismiss the activity
  And the live_activity_push_token should be cleared from the task record
  And the task status should NOT change (task may still be running)
  And a log entry should be recorded indicating the stale activity dismissal

When the user opens the app after the stale activity is dismissed
  And the task is still running
Then the app should show the task's current progress in TaskDetailView
  And the app MAY start a new local Live Activity (if supported)
  And the new Live Activity should register a fresh push token with the backend
```

---

## Scenario 3: Push token refresh — iOS token rotation

```
Given a task with status "testing"
  And the task has a registered live_activity_push_token "old-token-abc123"
  And the iOS app detects a new push token from Activity.pushTokenUpdates

When the iOS app calls PATCH /api/v1/tasks/{id}/live-activity
  with body {"push_token": "new-token-def456"}
Then the backend should update live_activity_push_token to "new-token-def456"
  And subsequent APNs Live Activity pushes should use "new-token-def456"
  And the response status code should be 200

When a progress update occurs after the token refresh
Then send_live_activity_update should be called with "new-token-def456"
  And the push should succeed (APNs 200)

When the iOS app sends the same token that is already stored
  (PATCH with push_token == current live_activity_push_token)
Then the backend should return 200 (idempotent, no error)
  And no unnecessary DB write should occur
```

---

## Scenario 4: Deep link from Live Activity tap

```
Given a task with id "task-uuid-1234"
  And the task has status "implementing"
  And a Live Activity is showing on the user's Dynamic Island or Lock Screen

When the user taps the Live Activity (expanded or compact view)
Then the app should open via a deep link URL: "rafraf://tasks/task-uuid-1234"
  And the app should navigate to TaskDetailView for that task
  And the TaskDetailView should display the current task status and progress

When the app was not running (cold start from Live Activity tap)
Then the app should handle the deep link in its onOpenURL handler
  And the app should authenticate the user (if needed) before showing TaskDetailView
  And the TaskDetailView should load the latest task state from GET /api/v1/tasks/{id}

When the user taps a Live Activity for a task that has already completed
Then the app should navigate to TaskDetailView showing the completed state
  And the result_summary should be visible
  And no Live Activity should remain active after the task is completed
```

---

## Scenario 5: Concurrent tasks with Live Activities

```
Given user has 3 active tasks:
  - Task A: status "planning", progress_pct 10
  - Task B: status "implementing", progress_pct 55
  - Task C: status "testing", progress_pct 80
  And each task has its own live_activity_push_token

When Task B receives a progress update (pct 60)
Then only Task B's Live Activity should be updated via APNs
  And Task A and Task C's Live Activities should remain unchanged

When Task C completes
Then Task C's Live Activity should receive an "end" event
  And Task C's live_activity_push_token should be cleared
  And a visible push notification should be sent for Task C
  And Task A and Task B's Live Activities should remain active

When all 3 tasks complete
Then all Live Activities should be dismissed
  And 3 separate visible push notifications should be sent (one per task)
```

---

## Scenario 6: Push service unavailable — graceful degradation

```
Given a running task with a live_activity_push_token
  And the APNs service is temporarily unreachable (network timeout)

When a progress update triggers a Live Activity push
Then the push attempt should fail gracefully (catch the exception)
  And the task should NOT transition to "failed" due to push failure
  And the task status should remain unchanged (e.g. still "implementing")
  And the error should be logged with structlog
  And the WebSocket broadcast should still be sent successfully

When APNs recovers and the next progress update occurs
Then the Live Activity push should succeed normally
  And no previously queued pushes need to be retried (latest state is sufficient)
```
