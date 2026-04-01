# Live Activity Push Scenarios — Sprint 2

Acceptance criteria for the LiveActivityPushService and its integration
with TaskOrchestratorService.

---

## Scenario 1: Live Activity update flow

```
Given a task with status "implementing"
  And the task has a valid live_activity_push_token
  And the current_step is "developer"

When TaskOrchestratorService.update_progress() is called with pct=50
Then LiveActivityPushService.send_live_activity_update() should be called
  And the APNs payload should contain:
    - aps.timestamp: integer (Unix epoch)
    - aps.event: "update"
    - aps.content-state.status: "implementing"
    - aps.content-state.currentStep: matches the detail text
    - aps.content-state.progress: 0.5
    - aps.content-state.completedSteps: integer
    - aps.content-state.totalSteps: integer
    - aps.content-state.phaseIcon: SF Symbol name string
  And the top-level payload should contain stale-date > current timestamp
  And the APNs headers should include:
    - apns-push-type: "liveactivity"
    - apns-topic: "com.atknatk.rafraf.push-type.liveactivity"
    - apns-priority: "10" or "5"
```

---

## Scenario 2: Rate limiting (throttle)

```
Given a task with status "implementing"
  And the task has a valid live_activity_push_token
  And the throttle window is 30 seconds

When 5 rapid update_progress() calls are made within 5 seconds
Then only 1 APNs push should be sent
  And the remaining 4 updates should be coalesced (silently dropped)

When 31 seconds pass after the first push
  And another update_progress() is called
Then a second APNs push should be sent
  And it should contain the latest content-state values
```

---

## Scenario 3: Task completion push

```
Given a task with status "reviewing"
  And the task has a valid live_activity_push_token
  And current_step is "reviewer"

When TaskOrchestratorService.complete_task() is called with a summary
Then a Live Activity end event should be sent:
    - aps.event: "end"
    - aps.dismissal-date: timestamp ~4 hours in the future
    - aps.content-state.status: "completed"
    - aps.content-state.progress: 1.0
  And a visible push notification should also be sent:
    - aps.alert.title: contains task title
    - aps.alert.body: contains the summary
```

---

## Scenario 4: Task failure push

```
Given a task with status "implementing"
  And the task has a valid live_activity_push_token

When TaskOrchestratorService.fail_task() is called with error "Build failed"
Then a Live Activity end event should be sent:
    - aps.event: "end"
    - aps.content-state.status: "failed"
  And a visible push notification should also be sent:
    - aps.alert should contain the error message
```

---

## Scenario 5: No push token — skip silently

```
Given a task with status "implementing"
  And the task has live_activity_push_token = null

When update_progress() is called
Then NO APNs push should be sent
  And no error should be raised
  And the task progress should still be updated in the database
```

---

## Scenario 6: Invalid token (APNs 410 Gone)

```
Given a task with a live_activity_push_token that has been invalidated
  And APNs responds with 410 Gone

When send_live_activity_update() is called
Then the service should mark the token as invalid
  And return False

When a subsequent push is attempted with the same token
Then the push should be skipped entirely (no APNs request made)
  And the service should return False
```

---

## Scenario 7: Timestamp monotonicity

```
Given two successive Live Activity updates for the same task

When the first update is sent with timestamp T1
  And the second update is sent with timestamp T2
Then T2 > T1 must hold
  And both timestamps should be Unix epoch integers
```
