# Anthropic `claude` CLI Upgrade Runbook (T3.8)

> Procedure for upgrading the Anthropic `claude` CLI on Mac bridge hosts.
> The bridge daemon spawns `claude -p --output-format stream-json` as a
> subprocess; bridge code parses the stream and forwards events to the
> backend. **Stale CLI = silent breakage.**
>
> **Cross-references:**
> - [`docs/10_Production_Pivot_Spec.md`](../10_Production_Pivot_Spec.md) §2 (Spike findings — Agent Teams flag), §4 (bridge architecture)
> - [`docs/11_Bridge_Spec.md`](../11_Bridge_Spec.md) §4 (claude subprocess mgmt), §5 (stream-json parser)
> - [`docs/12_Action_Plan_Tasks.md`](../12_Action_Plan_Tasks.md) §6 T3.8
> - [`docs/runbooks/deploy.md`](./deploy.md) §4 — bridge `.pkg` distribution
> - [`docs/runbooks/secret-rotation.md`](./secret-rotation.md) §3.4 — `ANTHROPIC_API_KEY` rotation (separate concern)
> - [`apps/rafraf-bridge/Makefile`](../../apps/rafraf-bridge/Makefile) — bridge build targets

---

## 1. Why this matters

Anthropic ships frequent updates to the `claude` CLI (often weekly):

- New `--output-format` schema fields (`stream-json` evolves)
- Behavioral changes to **Agent Teams** (still gated behind
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` as of 2026-05)
- Bug fixes that affect subprocess spawning, signal handling, exit codes
- Permission UX changes (e.g., new tool category, new approval prompt)

The bridge depends on:

1. **`claude --version`** existing on PATH
2. **`stream-json` event vocabulary** matching what
   `apps/rafraf-bridge/internal/claude/stream_parser.go` knows about
3. **Agent Teams subagent-spawn events** (`event.subagent.*`) being emitted
   when the env var is set
4. **Exit code semantics** (0 = clean, non-zero = error)

A silent CLI upgrade can break (1)-(4) without producing a Go panic — the
bridge will just log `stream_event_unknown_type` while data quietly falls
on the floor. **Detect and respond proactively.**

---

## 2. Weekly check

A scheduled check runs every Monday 09:00 UTC and posts to
`#rafraf-ops` if a new version is available.

### 2.1 Script: `infra/scripts/check-claude-cli.sh`

```bash
#!/usr/bin/env bash
#
# check-claude-cli.sh — compare local `claude --version` against the latest
# Anthropic release. Posts to Slack on mismatch. Intended to run as a
# launchd timer on each bridge host (or in CI for the canary bridge).
#
# Exit codes:
#   0 = up to date
#   1 = upgrade available (informational, not an error)
#   2 = local CLI missing or broken
#
set -euo pipefail

LOCAL_VER=$(claude --version 2>/dev/null | awk '{print $NF}' || echo "MISSING")

if [ "$LOCAL_VER" = "MISSING" ]; then
  echo "ERROR: claude CLI not found on PATH" >&2
  exit 2
fi

# Anthropic publishes the latest version in their installer JSON
LATEST_VER=$(curl -fsSL https://storage.googleapis.com/anthropic-cli/stable/version.json \
  | jq -r '.version' \
  || echo "UNKNOWN")

if [ "$LATEST_VER" = "UNKNOWN" ]; then
  echo "WARN: could not fetch latest version from Anthropic; skipping comparison" >&2
  exit 0
fi

echo "claude CLI: local=$LOCAL_VER  latest=$LATEST_VER"

if [ "$LOCAL_VER" = "$LATEST_VER" ]; then
  echo "Up to date."
  exit 0
fi

# Mismatch — post to Slack via incoming webhook
SLACK_WEBHOOK="${SLACK_WEBHOOK_OPS:-}"
if [ -n "$SLACK_WEBHOOK" ]; then
  curl -fsS -X POST "$SLACK_WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n \
      --arg host "$(hostname)" \
      --arg local "$LOCAL_VER" \
      --arg latest "$LATEST_VER" \
      '{
        text: ":warning: claude CLI upgrade available on \($host)",
        attachments: [{
          color: "warning",
          fields: [
            {title: "Local",  value: $local,  short: true},
            {title: "Latest", value: $latest, short: true},
            {title: "Runbook", value: "<https://github.com/atknatk/rafraf/blob/main/docs/runbooks/anthropic-cli-upgrade.md|anthropic-cli-upgrade.md>"}
          ]
        }]
      }')"
fi

exit 1
```

### 2.2 launchd schedule (per bridge host)

`~/Library/LaunchAgents/com.rafraf.bridge.claude-version-check.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.rafraf.bridge.claude-version-check</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/check-claude-cli.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>1</integer><!-- Monday -->
    <key>Hour</key><integer>9</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>EnvironmentVariables</key>
  <dict>
    <key>SLACK_WEBHOOK_OPS</key>
    <string>https://hooks.slack.com/services/...</string><!-- pulled from keychain in real install -->
  </dict>
  <key>StandardOutPath</key>
  <string>/tmp/rafraf-bridge-claude-version-check.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/rafraf-bridge-claude-version-check.err</string>
</dict>
</plist>
```

Load: `launchctl load ~/Library/LaunchAgents/com.rafraf.bridge.claude-version-check.plist`.

> The bridge `.pkg` installer (T0.5.12, see [`deploy.md`](./deploy.md) §4)
> drops both `check-claude-cli.sh` into `/usr/local/bin/` and the launchd
> plist into `~/Library/LaunchAgents/` automatically.

### 2.3 Manual check (one-off)

```bash
bash infra/scripts/check-claude-cli.sh
echo "exit=$?"
```

---

## 3. Upgrade procedure (Mac bridge host)

> **Pre-req:** the host must have `homebrew` installed and the bridge
> running under launchd. The bridge process must be stopped before the
> upgrade so it doesn't hold a file handle against the old `claude` binary.

### 3.1 Stop bridge

```bash
launchctl unload ~/Library/LaunchAgents/com.rafraf.bridge.plist
# Wait 5 s for the daemon to drain in-flight subprocesses
sleep 5
# Confirm it's gone
launchctl list | grep com.rafraf.bridge && echo "STILL RUNNING" || echo "stopped"
# Confirm no claude subprocess survives
pgrep -lf 'claude -p' && echo "ORPHAN CLAUDE PROC" || echo "clean"
```

If "ORPHAN CLAUDE PROC" appears, kill them: `pkill -f 'claude -p'`.

### 3.2 Backup `~/.claude/` config

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
tar -czf ~/Documents/rafraf-backups/claude-config-${TS}.tar.gz -C "$HOME" .claude
ls -lh ~/Documents/rafraf-backups/claude-config-${TS}.tar.gz
```

`~/.claude/` contains the user's CLI session history, project state, and
`usage.json`. The bridge depends on the directory layout being stable —
back it up so we can roll forward AND back.

### 3.3 Upgrade

```bash
# Homebrew path (preferred)
brew update
brew upgrade claude

# OR via the official installer:
curl -fsSL https://storage.googleapis.com/anthropic-cli/stable/install.sh | bash
```

### 3.4 Sanity test

```bash
# Version reports the new number
claude --version
# Expected: claude <NEW_VERSION>  (matches what check-claude-cli.sh expected)

# Simple query — text output
claude -p "echo test" --output-format text
# Expected: a one-line response, exit 0.

# Stream-json — the format the bridge actually consumes
claude -p "echo test" --output-format stream-json --verbose 2>&1 | head -20
# Expected: JSONL events. First line should be {"type":"system","subtype":"init",...}
# Last line should be {"type":"result","subtype":"success","is_error":false,...}

# Agent Teams flag (still experimental as of 2026-05)
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 \
  claude -p "Spawn 2 subagents that count to 5 in parallel" \
  --output-format stream-json --verbose 2>&1 | grep -E '"subtype":"agent_(spawn|complete)"' | head -5
# Expected: at least one agent_spawn event line. If empty, see §5 below.
```

If any sanity test fails, **immediately** roll back per §6 and report
in `#rafraf-ops`.

### 3.5 Re-load bridge

```bash
launchctl load ~/Library/LaunchAgents/com.rafraf.bridge.plist
# Wait for connection
sleep 3
# Verify connection log
tail -20 ~/Library/Logs/rafraf-bridge.log | grep -E 'connected|claude_binary_present'
```

### 3.6 Verify bridge `/healthz`

```bash
curl -sf http://localhost:9090/healthz | jq .
# Expected JSON shape:
# {
#   "status": "ok",
#   "claude_binary_present": true,
#   "claude_version": "<NEW_VERSION>",
#   "ws_connected": true,
#   "uptime_seconds": <small_number>
# }
```

If `claude_binary_present: false` → bridge cannot find `claude` on its
PATH. Check the launchd plist's `EnvironmentVariables.PATH` includes
`/opt/homebrew/bin` (Apple Silicon) or `/usr/local/bin` (Intel).

---

## 4. Stream-json schema drift detection

Even if upgrade sanity passes, behavioral drift can leak through. Watch
the bridge log for:

| Log event | Meaning | Action |
|---|---|---|
| `stream_event_unknown_type type=<X>` | Bridge parser does not recognize a new event type from the CLI | File issue against `apps/rafraf-bridge/internal/claude/stream_parser.go` to add the handler. NOT a rollback trigger unless event is critical (e.g., subagent_spawn). |
| `dispatch_event_no_handler event=<X>` | Backend received an event from bridge that no handler registered for | Cross-team — likely needs `apps/backend/app/services/claude_stream_manager.py` update too |
| `stream_json_parse_error line=<...>` | The line is not valid JSON, or schema mismatch (missing required field) | **Stop the bridge**, capture the line, file a P2 issue. Likely roll back. |
| `subagent_spawn_count == 0` for sessions that previously spawned subagents | Agent Teams flag may have been removed/renamed | See §5 |
| `claude_subprocess_exit code != 0` rate spike | New CLI returns non-zero in cases the old one didn't | Investigate per-session; may require feature flag or runner-side handling |

These are tracked in Grafana "RafRaf Bridge fleet" dashboard panels
"Unknown stream events (rate)" and "Subprocess exit codes".

### 4.1 Capturing a problematic stream

If you suspect a drift but the bridge log is sparse, capture a raw stream
locally on the bridge host:

```bash
TS=$(date +%s)
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 \
  claude -p "<reproducer prompt>" \
  --output-format stream-json --verbose \
  > /tmp/claude-stream-${TS}.jsonl 2>/tmp/claude-stream-${TS}.err

# Diff against a known-good capture (committed to apps/rafraf-bridge/testdata/)
diff <(jq -c 'keys' < apps/rafraf-bridge/testdata/02-agent-teams.jsonl | sort -u) \
     <(jq -c 'keys' < /tmp/claude-stream-${TS}.jsonl | sort -u)
```

The new event types or removed fields will show in the diff. Add
fixtures to `apps/rafraf-bridge/testdata/` and update the parser.

---

## 5. Agent Teams flag check

**As of 2026-05**, Agent Teams is still gated behind:

```
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

The bridge sets this in the subprocess env (see
`apps/rafraf-bridge/internal/claude/runner.go`). If Anthropic removes
the experimental flag (graduates to GA OR deprecates the feature), the
behavior changes:

| Future release behavior | Detection | Action |
|---|---|---|
| Flag becomes the default (GA) | Sanity test §3.4 still emits `agent_spawn` events without the env var | Update bridge to no longer set the flag (cosmetic); behavior unchanged |
| Flag renamed (e.g., `CLAUDE_CODE_AGENT_TEAMS`) | `subagent_spawn_count == 0` during sanity, no error | Update bridge to set new var, redeploy |
| Feature removed entirely | `subagent_spawn_count == 0`, possibly with `feature_unavailable` warning in stream | **Critical.** Roll back CLI per §6, file urgent issue, contact Anthropic |
| Flag still valid but new subagent event schema | `stream_event_unknown_type` from §4 | Update parser, redeploy bridge |

Always check Anthropic's release notes BEFORE upgrading:
https://docs.anthropic.com/claude-code/release-notes (or whichever URL
they use at the time). Search for "agent teams", "subagent",
"stream-json", "experimental".

---

## 6. Rollback

### 6.1 Homebrew rollback

Homebrew keeps the previous version's bottle for a short time:

```bash
# Stop bridge
launchctl unload ~/Library/LaunchAgents/com.rafraf.bridge.plist

# List installed versions
brew list --versions claude
# Expected: claude 1.5.4 1.5.3   <-- multiple versions present

# Switch to previous
brew unlink claude
brew install claude@1.5.3   # use whatever the prior version is
brew link --overwrite claude@1.5.3

# Verify
claude --version
# Expected: claude 1.5.3

# Restore ~/.claude/ from backup if config schema changed
TS=<from §3.2 step output>
rm -rf ~/.claude
tar -xzf ~/Documents/rafraf-backups/claude-config-${TS}.tar.gz -C "$HOME"

# Re-load bridge
launchctl load ~/Library/LaunchAgents/com.rafraf.bridge.plist

# Verify
curl -sf http://localhost:9090/healthz | jq .claude_version
```

If `brew install claude@<previous>` errors with "no such formula", the
versioned formula was not retained. Fall back to direct download:

```bash
# Download the previous installer (Anthropic keeps a /releases/<version>/ path)
curl -fsSL "https://storage.googleapis.com/anthropic-cli/releases/<previous>/install.sh" | bash
```

### 6.2 What if the previous version is unrecoverable?

- If the Homebrew bottle is gone and Anthropic does not retain the
  installer URL, the bridge is stuck on the new version. Two options:
  1. **Patch forward** — update bridge code to handle the new schema,
     redeploy bridge `.pkg` (per [`deploy.md`](./deploy.md) §4). Hours.
  2. **Disable Agent Teams** temporarily — set
     `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0` in launchd plist, restart
     bridge. Single-agent flow continues to work. Communicate the
     degraded state via in-app banner.

### 6.3 Communicate

Post in `#rafraf-ops`:

```
Rolled back claude CLI on <hostname> from <new> → <previous>.
Reason: <one-liner — e.g., "stream_json_parse_error rate spiked post-upgrade">
Bridge healthz: ok, claude_version=<previous>.
Issue: #<gh-issue-link>
```

---

## 7. Drill schedule — try-before-prod

Bridge upgrades **always** run through this sequence:

| Phase | Where | Duration | Pass criteria |
|---|---|---|---|
| **1. Dev bridge** | The Abi's primary Mac (or designated dev host) | Same day Anthropic ships | §3.4 sanity passes, §4 no drift events for 1 h |
| **2. Soak (24 h)** | Dev bridge runs normal workload | 24 h | No new error types in bridge log, healthz remains ok throughout, no spike in `stream_event_unknown_type` |
| **3. Canary user** | One opted-in beta user | 48-72 h | Same as soak + user reports no UX regression |
| **4. Phased rollout** | Beta tester pool | 7 days, 25%/50%/100% | Same + Sentry crash-free user % unchanged on iOS |
| **5. GA** | All bridges (auto-update via `download.rafraf.app/bridge/manifest.json`) | Continuous | Maintain Grafana panels |

> **Hot-fix exception:** if Anthropic ships a security patch (CVE), skip
> phases 1-4 and roll all bridges within 24 h, accepting the risk of
> behavioral drift in exchange for closing the CVE window. Communicate
> via in-app banner.

---

## 8. Owner & Last Reviewed

- **Owner:** Bridge owner (currently The Abi); dev/ops backup: SRE lead.
- **Last reviewed:** 2026-05-02 (initial creation, T3.8 / Faz 3)
- **Next review due:** 2026-08-02 (90 days; quarterly cadence — but
  practical review happens on every upgrade)
- **Change log:**

| Date | Author | Change |
|---|---|---|
| 2026-05-02 | T3.8 agent | Initial runbook — weekly check script, upgrade procedure (stop / backup / brew upgrade / sanity / re-load), stream-json drift detection table, Agent Teams flag policy, Homebrew rollback path, try-before-prod drill ladder |

---

**End of runbook.** Use §3 for the upgrade itself. §4 + §5 are the
"watch this on every upgrade" checklists. §6 is for when things go bad.
</content>
</invoke>