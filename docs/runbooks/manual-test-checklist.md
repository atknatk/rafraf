# Manual Test Checklist — TestFlight Builds (T3.4 / T3.8)

> Pre- and post-TestFlight manual smoke + soak checklist for iOS builds.
> Run this **before** promoting a build from internal → external testers
> (per [`deploy.md`](./deploy.md) §5), and **after** the build has been
> in users' hands for ≥ 3 hours soak time.
>
> **Cross-references:**
> - [`docs/10_Production_Pivot_Spec.md`](../10_Production_Pivot_Spec.md) §8 — Faz 3 launch criteria (crash-free %99+)
> - [`docs/12_Action_Plan_Tasks.md`](../12_Action_Plan_Tasks.md) §6 T3.4 (manual device test) + T3.8 (this runbook)
> - [`docs/04_iOS_App_Specification.md`](../04_iOS_App_Specification.md) — feature contract reference
> - [`docs/runbooks/deploy.md`](./deploy.md) §5 — TestFlight promote flow
> - [`docs/runbooks/anthropic-cli-upgrade.md`](./anthropic-cli-upgrade.md) — bridge sanity for tests that span Mac

---

## 1. Scope

### What this checklist covers

- **Pre-flight smoke** — basic functional verification before promote
  (15-30 min)
- **Functional grid** — feature-by-feature verification (60-90 min)
- **Performance** — cold start, warm start, scroll smoothness, memory
- **Network conditions** — Wi-Fi/4G transition, airplane, slow 3G, WS reconnect
- **Edge cases** — backend offline, bridge offline, rate-limit, session expired
- **Accessibility** — VoiceOver, Dynamic Type, ReduceMotion, contrast
- **3-hour soak** — leave app running in real-world use; capture metrics
- **Crash reporting** — Sentry/Crashlytics counts pre- vs post-build

### What this checklist does NOT cover

- **Backend correctness** — that's covered by `apps/backend/tests/`
- **Bridge correctness** — that's covered by `apps/rafraf-bridge/integration_test.go`
- **Cross-account scenarios** — multi-tenant tests are out-of-scope for V1
- **Localization completeness** — covered by lint-localizable script in CI
- **App Store review** — separate process; this checklist is for
  internal/external TestFlight only

### Pass criteria for promote

- All §3 functional rows pass on **two** physical devices (one current iPhone,
  one minimum-supported iPhone — currently iPhone 12 / iOS 17)
- §4 performance: all numeric thresholds met
- §5 network: app recovers from each disruption within stated SLA
- §7 accessibility: no critical or serious issue (per Xcode Accessibility Inspector)
- §8 crash-free users ≥ **99.0%** over the 3 h soak (per
  `docs/10_Production_Pivot_Spec.md` §8)
- Sign-off (§10) signed by tester + iOS lead

---

## 2. Pre-flight setup

| # | Step | Notes |
|---|---|---|
| 1 | Install build via TestFlight | `TestFlight.app` → "Update" / "Install"; record build number |
| 2 | Uninstall any prior build first (clean state) | Removes UserDefaults, Keychain entries, cached files. Required for cold-start tests |
| 3 | Sign in via Apple Sign In | Use a dedicated test Apple ID, not personal |
| 4 | Note settings: VoiceOver OFF, Dynamic Type default, Wi-Fi connected | Baseline; we'll vary these in §5/§7 |
| 5 | Device idle ≥ 5 min before tests | Cold start needs cold-OS state |
| 6 | Open Xcode → Window → Devices and Simulators → tail Console for the device | So you can see crash logs in real-time |
| 7 | Open Sentry / Crashlytics dashboard | For §8 baseline count BEFORE you start |
| 8 | Pair / verify the bridge is online | iOS Settings → Bridge → "Connected ✓"; if offline, fix bridge first or skip bridge-dependent rows |

**Test devices required:**

| Device | Role |
|---|---|
| iPhone 15 Pro (iOS 18+) | Primary — full grid |
| iPhone 12 (iOS 17.x — minimum supported) | Compatibility — abbreviated grid |
| iPad Air (iOS 17+) | Optional — for layout sanity if iPad layout active |

---

## 3. Functional test grid

For each row: **Tester records pass/fail and notes** in the §10 sign-off.
Block on any FAIL — promote does not proceed.

### 3.1 Auth

| # | Test | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| A1 | Tap "Sign in with Apple", complete Face ID prompt | Lands on Home; user profile populated with Apple display name | | |
| A2 | Background app for 16+ minutes (longer than `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15`), foreground | App silently refreshes JWT and continues; no re-login prompt | | |
| A3 | Force-kill app, re-launch | Auto-signs in via stored refresh token; lands on Home | | |
| A4 | Sign out from Settings | Returns to login screen; UserDefaults cleared (verify next launch shows login) | | |
| A5 | Sign in again after sign-out | Same flow as A1 (no orphaned state) | | |
| A6 | iOS revokes Apple ID (Settings → Apple ID → Password & Security → Apps Using Apple ID → RafRaf → "Stop Using Apple ID") | Next API call returns 401; app surfaces re-login screen with explanatory message | | |

### 3.2 Home

| # | Test | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| H1 | After login, session list loads | List populated within 2 s; sessions sorted newest-first | | |
| H2 | Each session row displays AI-generated title (T1.8 — `event.session.title` after first response) | Title is meaningful (not "Untitled" placeholder) for sessions that have ≥ 1 user message | | |
| H3 | Pull-to-refresh | Triggers REST refresh; list updates without flicker | | |
| H4 | Tap "Search" | Search bar appears; typing 3+ chars filters list | | |
| H5 | Sort menu — newest, oldest, by project | Sort order changes; selection persists across app relaunch | | |
| H6 | Empty state (new user, no sessions) | Friendly empty-state graphic + CTA to start a new session | | |
| H7 | Long-press a session row | Context menu: rename, archive, delete; each action behaves and persists server-side | | |

### 3.3 Chat

| # | Test | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| C1 | Open a session, type "hello" + send | Message appears in user bubble immediately; assistant bubble starts streaming within 2 s | | |
| C2 | Streaming token-by-token render | Tokens appear in real time, no "Loading..." spinner during stream | | |
| C3 | Code block in response — triple backtick syntax | Renders in monospace, syntax highlighted, with copy-to-clipboard button | | |
| C4 | Markdown response — bold, italic, lists, links | Renders correctly; links open in Safari (or in-app browser) | | |
| C5 | Long response (> 1000 tokens) | Scrolls smoothly while streaming; auto-scroll to bottom unless user has scrolled up | | |
| C6 | Send message while another response is streaming | New message queued; sends after current response completes | | |
| C7 | Cancel an in-flight response (tap X / pull down) | Stream stops within 1 s; partial response remains visible with "(cancelled)" tag | | |
| C8 | Copy assistant message via long-press | Plain-text copied to clipboard | | |

### 3.4 Agent (subagent tree, T1.7)

| # | Test | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| AG1 | Send a prompt that triggers Agent Teams (e.g., "spawn 3 subagents that each summarize a different file") | Within 5 s, subagent tree view appears with 3 nodes in "spawning" state | | |
| AG2 | Watch progress | Each subagent transitions: spawning → running → completed; progress % updates live | | |
| AG3 | Tap a subagent node | Drill-down view shows that subagent's individual log/output | | |
| AG4 | Subagent fails (e.g., due to permission denial) | Node marked as "failed" with error tag; parent task continues if other subagents OK | | |
| AG5 | Total cost displayed for the multi-agent task | Cost matches sum of subagent costs (within rounding) | | |

### 3.5 RFUsageGauge (5h / 7d, T2.5)

| # | Test | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| U1 | Open Home → RFUsageGauge visible | Two arcs — 5h and 7d — both showing current % usage | | |
| U2 | Color thresholds: < 70% green, 70-90% yellow, > 90% red | Verify by checking against current account state; document color shown | | |
| U3 | Overage state (> 100%) | Gauge shows red with "Over limit" caption; new task spawn prompts user to confirm | | |
| U4 | Tap gauge for detail sheet | Sheet shows 5h/7d numbers, last sync timestamp, breakdown by session | | |
| U5 | VoiceOver reads gauge | Full label: "Usage gauge: 5 hour 32 percent, 7 day 18 percent" (or similar) | | |
| U6 | Background → foreground triggers refresh | Latest usage poll happens within 5 s of foreground; gauge updates if changed | | |

### 3.6 Approval (write/bash tools)

| # | Test | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| AP1 | Send prompt that requires `Write` tool (e.g., "create a hello.txt file") | Approval sheet appears within 2 s with file path + content preview | | |
| AP2 | Tap "Approve" | Sheet dismisses; tool runs; result returns to chat | | |
| AP3 | Tap "Deny" | Sheet dismisses; chat shows "User denied" message; task continues with denial in context | | |
| AP4 | Approval timeout (do nothing for 60 s) | Sheet auto-dismisses with denial; task notified; configurable in iOS Settings | | |
| AP5 | Multiple sequential approvals (chained edits) | Each approval sheet appears after prior is decided; no race / stuck state | | |
| AP6 | `Bash` tool approval shows command + working dir | Sheet renders the full command with shell-style formatting | | |
| AP7 | Approval while app backgrounded (push delivers) | Push notification "RafRaf wants to run a command — tap to review" launches app to approval sheet | | |

### 3.7 Notifications (APNs + Live Activity)

| # | Test | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| N1 | First launch: notification permission prompt | Standard iOS dialog; tap "Allow" | | |
| N2 | Send a long-running task; lock device | Live Activity appears on Lock Screen with progress | | |
| N3 | Live Activity in Dynamic Island (compact) | Pill shows task icon + % | | |
| N4 | Live Activity in Dynamic Island (expanded — long-press) | Full UI: task title, progress bar, current step | | |
| N5 | Task completes — Live Activity ends | Activity dismisses cleanly within 5 s of completion | | |
| N6 | Push notification on task complete (app backgrounded) | Notification with task title + result preview | | |
| N7 | Tap notification | App launches to the relevant session | | |
| N8 | Notification with category "approval_required" | Push delivers immediately (per AP7) | | |

### 3.8 Settings

| # | Test | Expected | Pass/Fail | Notes |
|---|---|---|---|---|
| S1 | Settings tab loads | All sections present: Profile, Bridge, Notifications, Appearance, About | | |
| S2 | Profile shows correct name + Apple ID email | Matches the signed-in account | | |
| S3 | Bridge section shows connection status | "Connected" with last-seen timestamp; or "Disconnected" with "Re-pair" CTA | | |
| S4 | Notifications toggle | Disabling stops new push deliveries (verify by triggering a complete event) | | |
| S5 | Appearance: light/dark/system | Switch is immediate; tab bar + chat re-render correctly | | |
| S6 | About → Version | Shows correct marketing version + build number (matches TestFlight metadata) | | |
| S7 | Sign out (already covered A4); confirm Settings shows login state correctly | | | |

---

## 4. Performance

| # | Metric | Target | How to measure |
|---|---|---|---|
| P1 | Cold start (first launch after install / device reboot) | < 2.0 s to interactive Home | Stopwatch from icon tap to Home list rendered; OR Xcode Instruments "App Launch" template |
| P2 | Warm start (re-launch within 5 min) | < 500 ms to interactive Home | Same |
| P3 | Chat scroll FPS | ≥ 58 FPS (60 nominal) over 100+ messages | Xcode Instruments "Animation Hitches"; or visually verify no jank |
| P4 | Memory steady-state | < 200 MB after 30 min mixed use | Xcode Memory gauge during use |
| P5 | Memory after 3 h soak (§9) | < 250 MB; no monotonic growth (leak) | Xcode Memory gauge at end of soak |
| P6 | Battery drain — 1 h foreground | < 15% drain on iPhone 15 Pro at 50% brightness | Settings → Battery → Last 24 h |
| P7 | WS reconnect time after backgrounding 60 s | < 2 s | Watch debug log for `ws_connected=true` event |

If any of P1-P7 fail, log the deviation in §10 and decide with iOS lead
whether to block promote or accept (small regression with explanation
acceptable; > 25% degradation blocks).

---

## 5. Network conditions

Use Apple's Network Link Conditioner (Settings → Developer → Network Link
Conditioner; install Developer profile if missing) for slow-3G simulation.

| # | Scenario | Expected | Pass/Fail |
|---|---|---|---|
| NW1 | Wi-Fi → 4G handoff (walk out of Wi-Fi range) | Active WS reconnects within 3 s; current message stream resumes or restarts cleanly | |
| NW2 | Airplane mode ON during message stream | App shows "Offline" indicator within 5 s; when airplane mode OFF, reconnects + retries failed message | |
| NW3 | Slow 3G profile | Streaming response shows tokens slowly but no timeouts; cancel button responsive | |
| NW4 | Spotty Wi-Fi (lossy, 5% packet loss) | WS reconnects up to 3 times before surfacing user-visible error | |
| NW5 | Backend returns 503 (simulate by stopping pod or use staging maintenance window) | App shows "Service unavailable, retrying..." banner; auto-retries with exponential backoff | |
| NW6 | Bridge goes offline mid-task | App shows "Bridge unavailable" banner; in-flight task marked failed; user can retry | |

---

## 6. Edge cases

| # | Scenario | Expected | Pass/Fail |
|---|---|---|---|
| E1 | Backend offline at app launch | Login fails gracefully with "Cannot reach server, check connection"; no infinite spinner | |
| E2 | Bridge offline at task spawn | Task immediately marked failed with "Bridge offline" reason; user can re-pair from Settings | |
| E3 | Rate limit reached (claude_5h_usage_pct > 100) | Send button shows "Rate limited" tooltip; tap shows "Try again at <reset_time>" | |
| E4 | Anthropic CLI returns 429 (over-budget) | Backend surfaces 429 with `X-Bridge-Backoff` header; iOS shows "Anthropic temporarily limiting; retrying in N s" + auto-retry | |
| E5 | Session expired POST grace (legacy HS256 token rejected) | Per `jwt-key-rotation.md` §5 — app surfaces "Session expired, please sign in again" + clears state | |
| E6 | Background → foreground 5+ times in a row | Each foreground reconnects WS without leaking prior connection (check `lsof` count if instrumented; otherwise visual smoke) | |
| E7 | Open the app during a phone call (split UI) | UI scales correctly; no overlap with green status bar | |
| E8 | Storage full on device | Cached files cleanup triggers; chat continues to function (degraded — no offline cache) | |
| E9 | Receive a malformed event from backend (test with debug build that injects bad JSON) | App ignores the event with debug log; no crash | |
| E10 | Time-skew device (set device clock 1 h forward) | JWT not rejected as "expired" prematurely; app handles with leeway window per `apps/backend/app/core/security.py` | |

---

## 7. Accessibility

Run with **VoiceOver ON** for the entire grid; record any element that
does not announce sensibly.

| # | Test | Expected | Pass/Fail |
|---|---|---|---|
| AC1 | VoiceOver navigation through Home | Every row announces session title + project + last message preview | |
| AC2 | VoiceOver in chat | Each message bubble announces "User said:" or "Assistant said:" + content | |
| AC3 | Approval sheet | Announces tool name, target file, and "Double tap Approve to allow" | |
| AC4 | Dynamic Type at xxxLarge | All text scales; no truncation in chat bubbles, list rows, settings rows | |
| AC5 | Dynamic Type at smallest | Layout still functional, no overflow | |
| AC6 | Reduce Motion ON | Live Activity transitions, push reveals, gauge sweeps all use crossfade not slide | |
| AC7 | Color contrast — light mode | All text vs background WCAG AA (≥ 4.5:1 for body, ≥ 3:1 for large) — verify with Xcode Accessibility Inspector "Color Contrast" check | |
| AC8 | Color contrast — dark mode | Same | |
| AC9 | Bold Text ON (Settings → Display & Brightness → Text Size) | App respects + remains readable | |
| AC10 | Switch Control basic navigation (5 min spot-check) | Can tab through key UI without dead ends | |

---

## 8. Crash reporting

Track Sentry (or Crashlytics, depending on what's wired by T3.x) counts
across the build.

| # | Step | Expected |
|---|---|---|
| 8.1 | **Pre-test snapshot** — In Sentry, filter `release:<build-version>`. Note crash count, affected user count, crash-free users %. | Baseline numbers (typically zero for a fresh build) |
| 8.2 | Run §3-§7 grid | New crashes (if any) appear in Sentry within 60 s of crash |
| 8.3 | **Post-test snapshot** | Compare to 8.1; new crashes? List each fingerprint |
| 8.4 | Triage new crashes | Each must have: (a) reproducer steps, (b) severity (P0/P1/P2/P3), (c) issue link |
| 8.5 | Block promote on P0/P1 crashes | Yes — fix forward before promote |
| 8.6 | After 3 h soak (§9), final snapshot | Crash-free users ≥ 99.0% — if below, **block promote**; if 99.0-99.5%, document and decide with iOS lead |

---

## 9. 3-hour soak

Per Doc 10 §8 ("3 saat smoke, crash-free %99+"), the build must endure
real-world use for 3 hours before promote.

### 9.1 Setup

- Phone in pocket OR on desk in active use
- Battery starts at ≥ 80%
- Sentry dashboard open in another window
- Xcode Console attached for the duration (USB-tethered) OR rely on
  Sentry / TestFlight crash logs

### 9.2 Activity profile (split across the 3 h)

| Time | Activity |
|---|---|
| 0:00 - 0:30 | Active chat use — 10+ messages, 2+ sessions, code-block responses |
| 0:30 - 1:00 | Backgrounded (other apps), occasional notification check |
| 1:00 - 1:30 | Active again — trigger Live Activity, multi-agent task |
| 1:30 - 2:00 | Backgrounded with screen off (passive — phone in pocket) |
| 2:00 - 2:30 | Active — settings exploration, sign out + sign in, search |
| 2:30 - 3:00 | Mixed — alternate background/foreground every 5 min |

### 9.3 Post-soak checks

| # | Check | Pass criteria |
|---|---|---|
| SK1 | Sentry crash-free users % | ≥ 99.0% (per Doc 10 §8) |
| SK2 | Battery drain | Reasonable for use pattern (no thermal warning, no abnormal drain pattern) |
| SK3 | Memory not climbing | Final memory ≤ 250 MB, not double the steady-state baseline |
| SK4 | All WS reconnects logged | Bridge log shows expected disconnect/reconnect events; no "stuck disconnected" gap > 30 s during foreground |
| SK5 | Notifications still delivering | Send a test push at end of soak — confirm delivered within 30 s |
| SK6 | App still responsive | Open chat, send a message, get response — no degraded-state hang |
| SK7 | No backgrounded-task hangs in console | No `Watchdog` or `Memory pressure terminating` log entries |

---

## 10. Sign-off template

Fill in and commit this filled template to
`docs/runbooks/manual-test-runs/<YYYY-MM-DD>-build<NNN>.md` for every
TestFlight build that goes through this checklist.

```markdown
# Manual Test Sign-Off — Build <NNN>

**Date:** YYYY-MM-DD
**Build:** v<x.y.z> (<NNN>)
**Tester:** <name + GitHub handle>
**Backup tester:** <name>
**Devices:**
- iPhone <model>, iOS <version>
- iPhone <model> (min-supported), iOS <version>

## Pre-flight (§2)
- [ ] All steps completed

## Functional (§3)
- Auth: <PASS / FAIL with row IDs of failures>
- Home: <...>
- Chat: <...>
- Agent: <...>
- RFUsageGauge: <...>
- Approval: <...>
- Notifications: <...>
- Settings: <...>

## Performance (§4)
| ID | Metric | Target | Measured | Pass? |
|---|---|---|---|---|
| P1 | Cold start | < 2.0 s | <X.X s> | [ ] |
| P2 | Warm start | < 500 ms | <X ms> | [ ] |
| ... | | | | |

## Network (§5)
- NW1: <PASS / FAIL — note>
- NW2: <...>
- ...

## Edge cases (§6)
- E1-E10: <PASS list / FAIL list with notes>

## Accessibility (§7)
- AC1-AC10: <PASS list / FAIL list>
- Critical / serious issues from Accessibility Inspector: <count + summary>

## Crash reports (§8)
- Pre-test crash count: <N>
- Post-test crash count: <N>
- New crashes (fingerprint + Sentry link):
  1. <fingerprint> — <severity> — <#issue-link>

## 3-hour soak (§9)
- Started: YYYY-MM-DD HH:MM
- Ended: YYYY-MM-DD HH:MM
- Crash-free users %: <NN.N%>
- Battery drain: <NN%>
- Memory final: <NNN MB>
- WS reconnect count: <N>
- Other notes: <...>

## Promote decision

- [ ] **PROMOTE** — all criteria met
- [ ] **PROMOTE WITH NOTES** — minor issues documented for next build
- [ ] **BLOCK** — see action items below

## Action items

| # | Issue | Severity | Owner | Tracking |
|---|---|---|---|---|
| 1 | <description> | P0/P1/P2 | @<owner> | #<issue> |

## Sign-off

- Tester: ____________________  Date: ____________
- iOS lead: __________________  Date: ____________
```

---

## 11. Owner & Last Reviewed

- **Owner:** iOS lead (currently The Abi) + designated QA tester per build.
- **Last reviewed:** 2026-05-02 (initial creation, T3.8 / Faz 3, scoped from T3.4 manual device test requirements)
- **Next review due:** 2026-08-02 (90 days; quarterly cadence — but
  realistically, every Faz 3+ release gets a re-read)
- **Change log:**

| Date | Author | Change |
|---|---|---|
| 2026-05-02 | T3.8 agent | Initial checklist — pre-flight, 8-section functional grid (auth/home/chat/agent/usage/approval/notifications/settings), performance thresholds, network conditions, edge cases, accessibility, crash reporting, 3 h soak protocol, sign-off template |

---

**End of checklist.** Use §3 as the test grid; §10 as the deliverable.
</content>
</invoke>