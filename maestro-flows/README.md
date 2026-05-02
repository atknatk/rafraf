# RafRaf Maestro UI Test Flows

End-to-end iOS UI tests for the RafRaf approval pipeline, structured as
**modular** Maestro flows so each step can be run individually for debugging
or chained via `master.yaml` for full coverage.

## Files

| Flow                          | Purpose                                                                | Idempotent?           |
| ----------------------------- | ---------------------------------------------------------------------- | --------------------- |
| `00_onboarding_login.yaml`    | Walks onboarding (3x Next + Get Started) + signs in if needed          | Yes (handles 4 startup states) |
| `01_open_chat.yaml`           | Switches to Chat tab, picks first available agent/project (or stays in General Chat) | Yes (no-op if input visible) |
| `02_trigger_tool.yaml`        | Sends a Write-tool prompt that should trigger an approval sheet        | No (sends a fresh msg) |
| `03_capture_approval.yaml`    | Waits ≤35s for `RFApprovalSheet`, screenshots                          | No                    |
| `04_tap_allow_once.yaml`      | Taps "Allow once" decision button                                      | No                    |
| `master.yaml`                 | Chains 00 → 01 → 02 → 03 → 04 via `runFlow`                            | Partially             |

## Running

### Individually (for debugging)

```bash
~/.maestro/bin/maestro --device 4C381523-E855-488E-9111-C97B2FCBC9A6 test maestro-flows/02_trigger_tool.yaml
```

### Full suite

```bash
~/.maestro/bin/maestro --device 4C381523-E855-488E-9111-C97B2FCBC9A6 test maestro-flows/master.yaml
```

### From a different directory

Maestro's `runFlow:` resolves paths relative to the file containing the
`runFlow` directive, so `master.yaml` works from any cwd as long as the
`maestro-flows/` directory layout is preserved.

## Assumptions

- iPhone 16 Pro simulator UDID `4C381523-E855-488E-9111-C97B2FCBC9A6`
- Backend at `http://127.0.0.1:8000` with user `atknphone@gmail.com`
- Bridge running with `claude_code` capability registered (host id derived
  from `os.Hostname()` — currently `MacBook-Pro-4.local`, previously
  `atakan-macbook`). Flows use a permissive regex selector
  `(?i).*(macbook|atakan|mac-pro).*` to tolerate either.
- iOS app installed at `app.rafraf.RafRaf` bundle id

Credentials live inline in `00_onboarding_login.yaml` — fine for local
dev, do NOT check into a public branch with real prod credentials.

## Startup state handling (flow 00)

After `simctl uninstall` + `install` the iOS app retains its **keychain**
entries (Apple's behavior — keychain is not in the app sandbox), so the app
auto-authenticates from persisted JWT tokens. Onboarding `@AppStorage` is
wiped though, so the user still sees the 4 onboarding screens. After "Get
Started" the app jumps **directly** to Home, skipping Sign In.

Flow 00 handles four startup states:

1. **Already authenticated** (Settings tab visible) — fall through.
2. **Fresh install / no keychain** — onboarding (4 screens) + Sign In.
3. **Onboarding completed, no auth** — just Sign In.
4. **Keychain pre-auth + onboarding wiped** — onboarding (4 screens), no
   Sign In screen, lands on Home directly.

The Sign In block is **guarded** by `visible: "Sign In"` so case 4 doesn't
fail.

## Routing without a project (flow 01)

The bridge derives its host id from `os.Hostname()`. On the test machine
that returns `MacBook-Pro-4.local`. The test database has **zero**
`AgentProject` rows linking the new bridge id to any project, so the
`RFProjectPicker` SwiftUI Menu shows only the "General Chat" entry without
any agent submenu.

This is fine because `OrchestratorService._resolve_agent_for_project`
**falls back to any online claude_code agent** when the project lookup
returns nothing. The Write prompt still routes to the bridge → `claude` →
PreToolUse hook → backend → iOS approval sheet.

Flow 01 tries the agent submenu (regex `(?i).*(macbook|atakan|mac-pro).*`)
and only picks a project if a row appears. Otherwise it dismisses the
picker by tapping the navbar area and stays in General Chat mode. The
sanity assertion is just `Type your message...` visibility.

## Coordinate-based taps

Two taps are coordinate-driven instead of text-driven:

1. **Send button** in `02_trigger_tool.yaml` (`87%,57%`). The button is an
   SF Symbol (`arrow.up`) with no `.accessibilityLabel` — Maestro can't see
   it via text matcher. The chosen percent puts the tap on the orange circle
   when the keyboard is open. Re-measure if you change the prompt or the
   `RFChatInput` layout.
2. **Picker dismiss** in `01_open_chat.yaml` (`50%,15%`). Tapping the
   navbar area closes the SwiftUI Menu popover when no agent submenu was
   present. Avoids the tab bar (which would switch tabs).

## Known issues

- **30s approval timeout**: If `04_tap_allow_once.yaml` isn't run within
  ~30s of the sheet rendering, the broker request expires and the prompt
  is rejected. Re-run `02 → 03 → 04` cleanly back-to-back to avoid this.
- **Allow-Once → Write not creating file**: As of 2026-05-02 the iOS
  "Allow once" tap **dismisses the sheet but the broker UDS call doesn't
  get through** (bridge logs show `permission broker: request expired`
  even after iOS dismisses). Sheet visibility/dismissal works; write
  delivery is a separate backend bug not covered by these flows.
- **`approval.sheet.countdown N` rendered as raw key** in the sheet
  (visible as `approval.sheet.countdown 14` instead of "14s remaining").
  Localizable.xcstrings entry exists for `approval.countdown.remaining %lld`
  but the sheet uses a different key. iOS bug — not blocking.
