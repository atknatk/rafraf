package storage

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/config"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
)

// ---------------------------------------------------------------------------
// Test helpers — mockSink + config + temp-dir scaffolding.
// ---------------------------------------------------------------------------

// mockSink mirrors the pattern used in internal/claude/parser_test.go: each
// callback dispatches to an optional per-method hook so individual tests
// can assert by mutating their own counters / channels without subclassing.
type mockSink struct {
	mu sync.Mutex

	OnAITitleFn        func(protocol.EventStorageAITitle) error
	OnPRLinkFn         func(protocol.EventStoragePRLink) error
	OnHookAttachmentFn func(protocol.EventStorageHookAttachment) error
}

func (m *mockSink) OnAITitle(ev protocol.EventStorageAITitle) error {
	m.mu.Lock()
	fn := m.OnAITitleFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

func (m *mockSink) OnPRLink(ev protocol.EventStoragePRLink) error {
	m.mu.Lock()
	fn := m.OnPRLinkFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

func (m *mockSink) OnHookAttachment(ev protocol.EventStorageHookAttachment) error {
	m.mu.Lock()
	fn := m.OnHookAttachmentFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

// discardLogger returns a slog.Logger that drops every record. Tests rely
// on assertions against the sink, not on log output.
func discardLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

// newTestConfig wires a minimal *config.Config pointed at root with the
// production default 30-day cutoff. Validate is intentionally not called —
// the watcher only consumes the StorageWatcher subtree, and a fully-valid
// Config requires a backend_url that is irrelevant here.
func newTestConfig(root string, maxAgeDays int) *config.Config {
	return &config.Config{
		StorageWatcher: config.StorageWatcherConfig{
			Enabled:        true,
			ProjectsRoot:   root,
			MaxFileAgeDays: maxAgeDays,
		},
	}
}

// runWatcher launches a Watcher.Run in a goroutine bound to a fresh
// context, returning a cancel and a done-channel. Tests cancel + wait
// in t.Cleanup so a stuck Run never leaks across tests.
func runWatcher(t *testing.T, w *Watcher, sink Sink) (context.CancelFunc, <-chan error) {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- w.Run(ctx, sink) }()
	t.Cleanup(func() {
		cancel()
		select {
		case <-done:
		case <-time.After(2 * time.Second):
			t.Errorf("watcher did not shut down in time")
		}
	})
	return cancel, done
}

// appendLine writes one jsonl record followed by a newline to path,
// using O_APPEND so an open file handle on the watcher side does not
// interfere. Returns the encoded bytes for assertion convenience.
func appendLine(t *testing.T, path string, payload map[string]any) []byte {
	t.Helper()
	encoded, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}
	if _, err := f.Write(append(encoded, '\n')); err != nil {
		_ = f.Close()
		t.Fatalf("write %s: %v", path, err)
	}
	if err := f.Close(); err != nil {
		t.Fatalf("close %s: %v", path, err)
	}
	return encoded
}

// waitFor polls cond every 25 ms until it returns true or the deadline
// elapses. fsnotify on macOS (kqueue) typically delivers within ~10 ms,
// but CI machines with high load drift to ~100 ms — 2 s gives ~80 chances.
func waitFor(t *testing.T, label string, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(25 * time.Millisecond)
	}
	t.Fatalf("waitFor %q timed out", label)
}

// ---------------------------------------------------------------------------
// Pure parser tests — exercise the decoders directly so a schema regression
// surfaces independently of the fsnotify plumbing.
// ---------------------------------------------------------------------------

func TestParseAITitle(t *testing.T) {
	t.Parallel()

	raw := []byte(`{"type":"ai-title","sessionId":"sess-1","aiTitle":"Refactor auth flow"}`)
	ev, err := parseAITitle(raw)
	if err != nil {
		t.Fatalf("parse ai-title: %v", err)
	}
	if ev.SessionID != "sess-1" {
		t.Errorf("session id = %q, want %q", ev.SessionID, "sess-1")
	}
	if ev.Title != "Refactor auth flow" {
		t.Errorf("title = %q, want %q", ev.Title, "Refactor auth flow")
	}
}

func TestParseAITitle_BadJSON(t *testing.T) {
	t.Parallel()

	if _, err := parseAITitle([]byte("not-json")); err == nil {
		t.Fatal("parseAITitle accepted non-JSON")
	}
}

func TestParsePRLink(t *testing.T) {
	t.Parallel()

	raw := []byte(`{"type":"pr-link","sessionId":"sess-2","prNumber":42,"prUrl":"https://github.com/x/y/pull/42","prRepository":"x/y","ts":"2026-05-01T10:00:00Z"}`)
	ev, err := parsePRLink(raw)
	if err != nil {
		t.Fatalf("parse pr-link: %v", err)
	}
	if ev.SessionID != "sess-2" {
		t.Errorf("session id = %q", ev.SessionID)
	}
	if ev.PRNumber != 42 {
		t.Errorf("pr number = %d, want 42", ev.PRNumber)
	}
	if ev.PRURL != "https://github.com/x/y/pull/42" {
		t.Errorf("pr url = %q", ev.PRURL)
	}
	if ev.PRRepository != "x/y" {
		t.Errorf("pr repo = %q", ev.PRRepository)
	}
	if ev.Timestamp != "2026-05-01T10:00:00Z" {
		t.Errorf("ts = %q", ev.Timestamp)
	}
}

func TestParseHookAttachment_HookPrefix(t *testing.T) {
	t.Parallel()

	raw := []byte(`{"type":"attachment","sessionId":"sess-3","attachment":{"type":"hook_pre_tool_use","payload":{"tool":"Bash"}}}`)
	ev, ok, err := parseHookAttachment(raw)
	if err != nil {
		t.Fatalf("parse attachment: %v", err)
	}
	if !ok {
		t.Fatal("hook_ prefix should pass filter")
	}
	if ev.SessionID != "sess-3" {
		t.Errorf("session id = %q", ev.SessionID)
	}
	if ev.AttachmentType != "hook_pre_tool_use" {
		t.Errorf("attachment type = %q", ev.AttachmentType)
	}
	var payload map[string]string
	if err := json.Unmarshal(ev.Payload, &payload); err != nil {
		t.Fatalf("payload not raw json: %v", err)
	}
	if payload["tool"] != "Bash" {
		t.Errorf("payload.tool = %q, want Bash", payload["tool"])
	}
}

func TestParseHookAttachment_NonHookFiltered(t *testing.T) {
	t.Parallel()

	raw := []byte(`{"type":"attachment","sessionId":"sess-4","attachment":{"type":"screenshot","payload":{"url":"foo"}}}`)
	_, ok, err := parseHookAttachment(raw)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if ok {
		t.Fatal("non-hook attachment should be filtered out")
	}
}

// ---------------------------------------------------------------------------
// Integration tests — write fixtures into a tempdir and assert the watcher
// surfaces the right events to the sink.
// ---------------------------------------------------------------------------

func TestWatcher_AITitleEvent(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	projectDir := filepath.Join(root, "project-a")
	if err := os.MkdirAll(projectDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	jsonlPath := filepath.Join(projectDir, "session-x.jsonl")
	// Pre-create empty so the initial walk picks it up.
	if err := os.WriteFile(jsonlPath, []byte{}, 0o644); err != nil {
		t.Fatalf("create jsonl: %v", err)
	}

	var got atomic.Pointer[protocol.EventStorageAITitle]
	sink := &mockSink{
		OnAITitleFn: func(ev protocol.EventStorageAITitle) error {
			got.Store(&ev)
			return nil
		},
	}

	w := NewWatcher(newTestConfig(root, 30), discardLogger())
	runWatcher(t, w, sink)

	// Give Run a moment to perform its initial walk and register fsnotify
	// subscriptions before we trigger the first write.
	time.Sleep(100 * time.Millisecond)

	appendLine(t, jsonlPath, map[string]any{
		"type":      "ai-title",
		"sessionId": "sess-init",
		"aiTitle":   "First session title",
	})

	waitFor(t, "ai-title delivered", func() bool { return got.Load() != nil })

	ev := got.Load()
	if ev.SessionID != "sess-init" {
		t.Errorf("session id = %q, want %q", ev.SessionID, "sess-init")
	}
	if ev.Title != "First session title" {
		t.Errorf("title = %q", ev.Title)
	}
}

func TestWatcher_PRLinkEvent(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	jsonlPath := filepath.Join(root, "pr-session.jsonl")
	if err := os.WriteFile(jsonlPath, []byte{}, 0o644); err != nil {
		t.Fatalf("create jsonl: %v", err)
	}

	var got atomic.Pointer[protocol.EventStoragePRLink]
	sink := &mockSink{
		OnPRLinkFn: func(ev protocol.EventStoragePRLink) error {
			got.Store(&ev)
			return nil
		},
	}

	w := NewWatcher(newTestConfig(root, 30), discardLogger())
	runWatcher(t, w, sink)
	time.Sleep(100 * time.Millisecond)

	appendLine(t, jsonlPath, map[string]any{
		"type":         "pr-link",
		"sessionId":    "sess-pr",
		"prNumber":     7,
		"prUrl":        "https://github.com/atknatk/rafraf/pull/7",
		"prRepository": "atknatk/rafraf",
		"ts":           "2026-05-01T12:00:00Z",
	})

	waitFor(t, "pr-link delivered", func() bool { return got.Load() != nil })
	ev := got.Load()
	if ev.PRNumber != 7 || ev.PRRepository != "atknatk/rafraf" {
		t.Errorf("unexpected pr-link payload: %+v", ev)
	}
}

func TestWatcher_HookAttachmentFilter(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	jsonlPath := filepath.Join(root, "hooks.jsonl")
	if err := os.WriteFile(jsonlPath, []byte{}, 0o644); err != nil {
		t.Fatalf("create jsonl: %v", err)
	}

	var hookCount atomic.Int32
	var hookTypes []string
	var typesMu sync.Mutex
	sink := &mockSink{
		OnHookAttachmentFn: func(ev protocol.EventStorageHookAttachment) error {
			hookCount.Add(1)
			typesMu.Lock()
			hookTypes = append(hookTypes, ev.AttachmentType)
			typesMu.Unlock()
			return nil
		},
	}

	w := NewWatcher(newTestConfig(root, 30), discardLogger())
	runWatcher(t, w, sink)
	time.Sleep(100 * time.Millisecond)

	// Two attachments — one hook_*, one not. Only the hook_* should fire.
	appendLine(t, jsonlPath, map[string]any{
		"type":      "attachment",
		"sessionId": "sess-h",
		"attachment": map[string]any{
			"type":    "hook_post_tool_use",
			"payload": map[string]any{"tool": "Edit"},
		},
	})
	appendLine(t, jsonlPath, map[string]any{
		"type":      "attachment",
		"sessionId": "sess-h",
		"attachment": map[string]any{
			"type":    "screenshot",
			"payload": map[string]any{"url": "data:..."},
		},
	})

	waitFor(t, "hook attachment delivered", func() bool { return hookCount.Load() == 1 })

	// Give the watcher a small window to incorrectly fire on the second
	// attachment if the filter is broken.
	time.Sleep(150 * time.Millisecond)
	if got := hookCount.Load(); got != 1 {
		t.Errorf("hook count = %d, want 1", got)
	}
	typesMu.Lock()
	defer typesMu.Unlock()
	if len(hookTypes) != 1 || hookTypes[0] != "hook_post_tool_use" {
		t.Errorf("hook types = %v, want [hook_post_tool_use]", hookTypes)
	}
}

func TestWatcher_OldFileSkipped(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	oldPath := filepath.Join(root, "old.jsonl")
	// Pre-populate the file with an ai-title row so a naive watcher would
	// dispatch on initial scan if it failed to skip aged files.
	initial := []byte(`{"type":"ai-title","sessionId":"old-sess","aiTitle":"Should not fire"}` + "\n")
	if err := os.WriteFile(oldPath, initial, 0o644); err != nil {
		t.Fatalf("write old jsonl: %v", err)
	}
	old := time.Now().Add(-90 * 24 * time.Hour)
	if err := os.Chtimes(oldPath, old, old); err != nil {
		t.Fatalf("chtimes: %v", err)
	}

	var got atomic.Int32
	sink := &mockSink{
		OnAITitleFn: func(protocol.EventStorageAITitle) error {
			got.Add(1)
			return nil
		},
	}

	w := NewWatcher(newTestConfig(root, 30), discardLogger())
	runWatcher(t, w, sink)

	// Give the initial scan time to either correctly skip or (if the test
	// regresses) incorrectly dispatch.
	time.Sleep(300 * time.Millisecond)
	if got.Load() != 0 {
		t.Errorf("ai-title fired %d times for old file; want 0", got.Load())
	}
}

func TestWatcher_TailOffsetWorks(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	jsonlPath := filepath.Join(root, "tail.jsonl")

	// Pre-populate with two lines BEFORE the watcher starts. These should
	// be skipped (initial scan primes the offset at end-of-file).
	preexisting := `{"type":"ai-title","sessionId":"a","aiTitle":"first"}` + "\n" +
		`{"type":"ai-title","sessionId":"b","aiTitle":"second"}` + "\n"
	if err := os.WriteFile(jsonlPath, []byte(preexisting), 0o644); err != nil {
		t.Fatalf("write preexisting: %v", err)
	}

	type captured struct {
		mu      sync.Mutex
		titles  []string
		sessIDs []string
	}
	cap := &captured{}
	sink := &mockSink{
		OnAITitleFn: func(ev protocol.EventStorageAITitle) error {
			cap.mu.Lock()
			cap.titles = append(cap.titles, ev.Title)
			cap.sessIDs = append(cap.sessIDs, ev.SessionID)
			cap.mu.Unlock()
			return nil
		},
	}

	w := NewWatcher(newTestConfig(root, 30), discardLogger())
	runWatcher(t, w, sink)
	time.Sleep(150 * time.Millisecond)

	// Append a 3rd line — only this one should reach the sink.
	appendLine(t, jsonlPath, map[string]any{
		"type":      "ai-title",
		"sessionId": "c",
		"aiTitle":   "third",
	})

	waitFor(t, "third title delivered", func() bool {
		cap.mu.Lock()
		defer cap.mu.Unlock()
		return len(cap.titles) >= 1
	})

	// Pause then assert nothing else slipped through.
	time.Sleep(150 * time.Millisecond)
	cap.mu.Lock()
	defer cap.mu.Unlock()
	if len(cap.titles) != 1 {
		t.Fatalf("titles = %v, want exactly 1", cap.titles)
	}
	if cap.titles[0] != "third" {
		t.Errorf("title[0] = %q, want %q", cap.titles[0], "third")
	}
	if cap.sessIDs[0] != "c" {
		t.Errorf("sessID[0] = %q, want c", cap.sessIDs[0])
	}
}

// TestWatcher_NewFileAfterStart verifies the Create-event path: a jsonl
// file that did NOT exist at startup should still be picked up and tailed
// from the start (offset 0) once it appears.
func TestWatcher_NewFileAfterStart(t *testing.T) {
	t.Parallel()

	root := t.TempDir()

	var got atomic.Pointer[protocol.EventStorageAITitle]
	sink := &mockSink{
		OnAITitleFn: func(ev protocol.EventStorageAITitle) error {
			got.Store(&ev)
			return nil
		},
	}

	w := NewWatcher(newTestConfig(root, 30), discardLogger())
	runWatcher(t, w, sink)
	time.Sleep(100 * time.Millisecond)

	jsonlPath := filepath.Join(root, "fresh.jsonl")
	appendLine(t, jsonlPath, map[string]any{
		"type":      "ai-title",
		"sessionId": "sess-fresh",
		"aiTitle":   "fresh title",
	})

	waitFor(t, "fresh ai-title delivered", func() bool { return got.Load() != nil })
	if got.Load().SessionID != "sess-fresh" {
		t.Errorf("session id = %q, want sess-fresh", got.Load().SessionID)
	}
}

// TestWatcher_NilSinkRejected guards the API contract — a nil sink would
// nil-pointer-panic the dispatch path on the first event, so Run rejects
// it up front instead.
func TestWatcher_NilSinkRejected(t *testing.T) {
	t.Parallel()

	w := NewWatcher(newTestConfig(t.TempDir(), 30), discardLogger())
	err := w.Run(context.Background(), nil)
	if err == nil || err.Error() == "" {
		t.Fatalf("nil sink should be rejected, got err=%v", err)
	}
}

// TestWatcher_EmptyProjectsRootRejected is the symmetric guard: misconfig
// (forgetting projects_root) must surface a clear error rather than a
// silent no-op.
func TestWatcher_EmptyProjectsRootRejected(t *testing.T) {
	t.Parallel()

	cfg := &config.Config{
		StorageWatcher: config.StorageWatcherConfig{Enabled: true, MaxFileAgeDays: 30},
	}
	w := NewWatcher(cfg, discardLogger())
	err := w.Run(context.Background(), &mockSink{})
	if err == nil {
		t.Fatal("empty projects_root should be rejected")
	}
}
