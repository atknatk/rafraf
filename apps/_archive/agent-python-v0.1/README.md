# agent-python-v0.1 — Archived

This directory contains the v0.1 Python `host agent` implementation,
archived as part of [Faz 0 cleanup](../../../docs/12_Action_Plan_Tasks.md)
([T0.10](../../../docs/12_Action_Plan_Tasks.md)).

**Status:** ARCHIVED. Not built, not deployed, not tested in CI.

## Why preserved

Per [ADR-0003 — Rewrite host agent as Go bridge](../../../docs/adr/0003-rewrite-host-agent-as-go-bridge.md),
the host agent role was reduced to "claude bridge" only and re-implemented
in Go at [`apps/rafraf-bridge/`](../../rafraf-bridge/). This Python source is
preserved as a **reference implementation** during the Go port (Faz 0.5):

- `agent/runners/claude_runner.py` — 658-line stream-JSON parser + subprocess
  manager being ported to `apps/rafraf-bridge/internal/claude/`
- `agent/core/protocol.py` — WebSocket envelope schemas; bridge-track T0.5.4
  uses these as the contract for `internal/protocol/messages.go`
- `agent/security/` — shell whitelist/denylist patterns (informs
  `internal/security/sandbox.go`)
- `agent/core/connection.py` — outbound WS client patterns

## Lifecycle

This directory will be **fully deleted** once Faz 0.5 (bridge port) lands and
the Go bridge has feature-parity for V1 scope. Do not import from this path
in new code.

## Faz 0.5 progress

See [`docs/12_Action_Plan_Tasks.md`](../../../docs/12_Action_Plan_Tasks.md) §4
for the bridge port task list.
