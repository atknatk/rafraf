# rafraf-bridge

`rafraf-bridge` is the Go-based local bridge daemon that connects a developer's
Mac to the RafRaf backend. It supersedes the archived Python host agent
(`apps/_archive/agent-python-v0.1/`) and is responsible for:

- Maintaining the WebSocket session against the RafRaf backend control plane.
- Spawning the local `claude` CLI subprocess in stream-JSON mode and forwarding
  events to the backend.
- Watching `~/.claude/projects/` and `~/.claude/usage.json` for storage and
  statusline events.
- Packaging itself for distribution via launchd, Homebrew, and a signed `.pkg`.

## Specification

See `docs/11_Bridge_Spec.md` for the authoritative design (repo layout, package
contracts, WS protocol, packaging, configuration).

## Build / test / lint

```bash
make build   # produces ./bridge
make test    # runs go test ./...
make lint    # runs golangci-lint
make pkg     # placeholder until T0.5.12
make clean   # removes ./bridge
```

Requires Go 1.22+ and `golangci-lint`.

## Status

Faz 0.5 in progress — see `docs/12_Action_Plan_Tasks.md` T0.5.1+ for task
sequencing. This skeleton (T0.5.1) only establishes the module layout, tooling,
and a version-printing entry point; package logic lands in T0.5.2 onward.
