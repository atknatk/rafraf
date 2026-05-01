package claude

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// EnvelopeSender is the cross-package callback used by Runner to forward
// stream-JSON events upward. ws.Client.Send satisfies this signature.
type EnvelopeSender func(protocol.Envelope)

// Runner spawns `claude -p --output-format stream-json --verbose` and
// forwards each parsed event as a control-plane envelope.
//
// T0.5.5 will replace this with a richer EventSink-driven implementation
// (env injection, abort, structured errors). The current behavior is a
// verbatim port of the spike.
type Runner struct {
	Prompt         string
	Send           EnvelopeSender
	CWD            string
	PermissionMode string
}

// NewRunner constructs a Runner. send must be non-nil.
func NewRunner(prompt, cwd, permissionMode string, send EnvelopeSender) *Runner {
	return &Runner{
		Prompt:         prompt,
		CWD:            cwd,
		PermissionMode: permissionMode,
		Send:           send,
	}
}

// Run executes the claude subprocess and pumps stream-JSON lines into the
// envelope sink until the process exits or ctx is cancelled.
func (r *Runner) Run(ctx context.Context) error {
	telemetry.ClaudeSubprocesses.Add(1)
	defer telemetry.ClaudeSubprocesses.Add(-1)

	args := []string{
		"-p",
		"--output-format", "stream-json",
		"--verbose",
		"--include-partial-messages",
	}
	if r.PermissionMode != "" {
		args = append(args, "--permission-mode", r.PermissionMode)
	}
	args = append(args, r.Prompt)

	cmd := exec.CommandContext(ctx, "claude", args...)
	if r.CWD != "" {
		cmd.Dir = r.CWD
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("stdout pipe: %w", err)
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return fmt.Errorf("stderr pipe: %w", err)
	}
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start: %w", err)
	}

	// Stderr → log (drain to avoid blocking).
	go func() { _, _ = io.Copy(os.Stderr, stderr) }()

	// Stdout → parse + forward.
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 1<<20), 16<<20) // up to 16 MiB per line
	for scanner.Scan() {
		line := scanner.Bytes()
		telemetry.ClaudeLinesRead.Add(1)
		var ev StreamEvent
		if err := json.Unmarshal(line, &ev); err != nil {
			continue
		}
		ev.Raw = make(json.RawMessage, len(line))
		copy(ev.Raw, line)

		envType := mapType(ev.Type, ev.Subtype)
		if ev.Type == "rate_limit_event" {
			telemetry.ClaudeRateLimitHits.Add(1)
		}
		env := protocol.Envelope{
			Type:    envType,
			ID:      protocol.NewID(),
			TS:      protocol.NowISO(),
			Target:  "session:" + ev.SessionID,
			Payload: ev.Raw,
		}
		r.Send(env)
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("scan: %w", err)
	}
	if err := cmd.Wait(); err != nil {
		return fmt.Errorf("wait: %w", err)
	}
	return nil
}

func mapType(streamType, subtype string) string {
	switch streamType {
	case "system":
		return "event.session." + safeSub(subtype, "system")
	case "assistant":
		return "event.session.assistant"
	case "user":
		return "event.session.user"
	case "stream_event":
		return "event.session.stream"
	case "rate_limit_event":
		return "event.session.rate_limit"
	case "result":
		return "event.session.result"
	default:
		return "event.session.unknown"
	}
}

func safeSub(s, fallback string) string {
	if s == "" {
		return fallback
	}
	return s
}
