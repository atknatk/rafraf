#!/usr/bin/env python3
# Claude Code statusline script — RafRaf bridge usage tracker.
#
# Embedded into the rafraf-bridge Go binary via //go:embed and written
# to ~/.claude/statusline.py by InstallStatuslineScript (see
# apps/rafraf-bridge/internal/statusline/installer.go).
#
# Source / reference:
#   - docs/11_Bridge_Spec.md §8  (statusline watcher + installer design)
#   - docs/claude-code-usage-tracking.md §"Statusline Script
#     (referans implementation)"  (canonical script body, verbatim)
#   - docs/10_Production_Pivot_Spec.md §2.11  (usage tracking pipeline)
#
# Behaviour:
#   1. Read the statusline JSON Claude Code pipes to stdin on every
#      render (Claude Code v2.1.80+ includes a `rate_limits` field).
#   2. Persist 5h / 7d usage percentages and reset timestamps to
#      ~/.claude/usage.json so the Go bridge's statusline.Watcher can
#      poll the file (mod-time gated) and forward EventUsageReport
#      events to the backend.
#   3. Print a short single-line summary (model | 5h:NN% | 7d:NN%)
#      to stdout — this is what the user sees in the Claude Code UI.
import json
import os
import sys
import time

try:
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
except Exception:
    data = {}

rl = data.get("rate_limits") or {}
fh = (rl.get("five_hour") or {}).get("used_percentage")
sd = (rl.get("seven_day") or {}).get("used_percentage")

with open(os.path.expanduser("~/.claude/usage.json"), "w") as f:
    json.dump({
        "five_hour_pct": fh,
        "seven_day_pct": sd,
        "five_hour_resets_at": (rl.get("five_hour") or {}).get("resets_at"),
        "seven_day_resets_at": (rl.get("seven_day") or {}).get("resets_at"),
        "ts": int(time.time()),
        "raw": rl,
    }, f)

parts = []
model = (data.get("model") or {}).get("display_name")
if model:
    parts.append(model)
if fh is not None:
    parts.append(f"5h:{round(fh)}%")
if sd is not None:
    parts.append(f"7d:{round(sd)}%")
print(" | ".join(parts))
