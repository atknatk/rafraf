package storage

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/fsnotify/fsnotify"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/config"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// scannerInitialBufSize seeds the bufio.Scanner buffer at 1 MiB so typical
// jsonl lines never trigger an allocation. scannerMaxBufSize caps the
// per-line size at 16 MiB to match the runner's stream-json reader.
const (
	scannerInitialBufSize = 1 << 20
	scannerMaxBufSize     = 16 << 20
)

// Sink receives one callback per recognised, decoded storage event. The
// shape mirrors claude.EventSink so callers can implement either with the
// same struct (the bridge main loop will). Methods returning errors lets
// the sink propagate transport failures back to the watcher, but the
// watcher logs and continues — a single failed delivery must not abort
// the file-system tail loop.
type Sink interface {
	OnAITitle(ev protocol.EventStorageAITitle) error
	OnPRLink(ev protocol.EventStoragePRLink) error
	OnHookAttachment(ev protocol.EventStorageHookAttachment) error
}

// interestedTypes is the closed set of jsonl event types the watcher
// surfaces. attachment is in the set but is gated downstream by the
// hook_* prefix check inside parseHookAttachment so non-hook attachments
// (e.g. screenshots from other tools) are silently dropped.
var interestedTypes = map[string]bool{
	"ai-title":   true,
	"pr-link":    true,
	"attachment": true,
}

// Watcher tails .jsonl files under cfg.StorageWatcher.ProjectsRoot via
// fsnotify and dispatches the small subset of events listed in
// interestedTypes to the configured Sink. A single Watcher instance owns
// one fsnotify.Watcher and one tail-offset map; both are protected by mu
// because fsnotify callbacks may interleave with the initial walk on
// platforms whose backend (kqueue on macOS, inotify on Linux) is reentrant.
//
// See docs/11_Bridge_Spec.md §7 for the design rationale, including why
// we tail from end-of-file on initial scan (avoid replaying ancient
// history on every bridge start) and why old files are skipped entirely
// (the projects root averages 3.3 GB across 4474 files in production —
// most of it cold).
type Watcher struct {
	cfg    *config.Config
	logger *slog.Logger

	fsnotifyW   *fsnotify.Watcher
	tailOffsets map[string]int64
	maxFileAge  time.Duration

	mu sync.Mutex
}

// NewWatcher constructs a Watcher with the offsets map pre-allocated and
// maxFileAge derived from cfg.StorageWatcher.MaxFileAgeDays. logger may be
// nil; a discarding default is substituted to keep call sites uncluttered.
//
// The fsnotify watcher itself is created inside Run so a Watcher can be
// constructed cheaply (e.g. in dependency-injection wiring) without
// touching the kernel surface; constructor failure paths therefore only
// involve config validation, which Load() has already performed.
func NewWatcher(cfg *config.Config, logger *slog.Logger) *Watcher {
	if logger == nil {
		logger = slog.New(slog.NewTextHandler(io.Discard, nil))
	}
	return &Watcher{
		cfg:         cfg,
		logger:      logger,
		tailOffsets: make(map[string]int64),
		maxFileAge:  time.Duration(cfg.StorageWatcher.MaxFileAgeDays) * 24 * time.Hour,
	}
}

// Run starts the fsnotify watcher, performs an initial scan that primes
// tailOffsets from end-of-file for every recent jsonl, then enters the
// event loop until ctx is cancelled. A Run returns either ctx.Err() (the
// happy shutdown path) or an unrecoverable setup error. fsnotify-level
// errors are logged at warn and the loop continues — they are usually
// transient (file deleted between event and stat).
func (w *Watcher) Run(ctx context.Context, sink Sink) error {
	if sink == nil {
		return errors.New("storage: sink must not be nil")
	}
	if w.cfg.StorageWatcher.ProjectsRoot == "" {
		return errors.New("storage: projects_root is empty")
	}

	fsw, err := fsnotify.NewWatcher()
	if err != nil {
		return err
	}
	w.fsnotifyW = fsw
	defer func() { _ = w.fsnotifyW.Close() }()

	walkErr := filepath.Walk(w.cfg.StorageWatcher.ProjectsRoot, func(path string, info fs.FileInfo, walkErr error) error {
		return w.walkInitial(path, info, walkErr)
	})
	if walkErr != nil {
		// A missing root is not fatal — tests use a freshly created temp
		// dir that may not exist yet, and production may legitimately not
		// have ~/.claude/projects on first run. The fsnotify subscription
		// list will simply be empty until a Create event lands.
		if !os.IsNotExist(walkErr) {
			w.logger.Warn("storage: initial walk error", "err", walkErr)
		}
	}

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case event, ok := <-w.fsnotifyW.Events:
			if !ok {
				return errors.New("storage: fsnotify events channel closed")
			}
			w.handleFSEvent(event, sink)
		case fsErr, ok := <-w.fsnotifyW.Errors:
			if !ok {
				return errors.New("storage: fsnotify errors channel closed")
			}
			w.logger.Warn("storage: fsnotify error", "err", fsErr)
		}
	}
}

// walkInitial is the filepath.Walk callback used by Run. Directories are
// added to the fsnotify subscription so future Create events under them
// surface; jsonl files are primed in tailOffsets at their current size so
// only NEW lines after this point trigger dispatches. Files older than
// maxFileAge are skipped entirely.
//
// A walkErr arriving from filepath.Walk (e.g. permission denied on a
// single directory) is swallowed so a single bad subdirectory does not
// abort the entire scan.
func (w *Watcher) walkInitial(path string, info fs.FileInfo, walkErr error) error {
	if walkErr != nil {
		return nil
	}
	if info == nil {
		return nil
	}
	if info.IsDir() {
		if addErr := w.fsnotifyW.Add(path); addErr != nil {
			w.logger.Warn("storage: fsnotify add dir failed", "path", path, "err", addErr)
		}
		return nil
	}
	if !strings.HasSuffix(path, ".jsonl") {
		return nil
	}
	if w.maxFileAge > 0 && time.Since(info.ModTime()) > w.maxFileAge {
		return nil
	}
	w.mu.Lock()
	w.tailOffsets[path] = info.Size()
	w.mu.Unlock()
	return nil
}

// handleFSEvent reacts to one fsnotify event. Write events on .jsonl
// files trigger an incremental tail; Create events on directories grow
// the subscription set so newly created project subdirectories light up
// without a restart, and Create events on .jsonl files prime the tail
// offset at zero so the first line is captured.
func (w *Watcher) handleFSEvent(event fsnotify.Event, sink Sink) {
	if event.Op&fsnotify.Write == fsnotify.Write && strings.HasSuffix(event.Name, ".jsonl") {
		w.tailFile(event.Name, sink)
	}
	if event.Op&fsnotify.Create == fsnotify.Create {
		info, err := os.Stat(event.Name)
		if err != nil {
			return
		}
		if info.IsDir() {
			if addErr := w.fsnotifyW.Add(event.Name); addErr != nil {
				w.logger.Warn("storage: fsnotify add new dir failed", "path", event.Name, "err", addErr)
			}
			return
		}
		if strings.HasSuffix(event.Name, ".jsonl") {
			w.mu.Lock()
			if _, exists := w.tailOffsets[event.Name]; !exists {
				w.tailOffsets[event.Name] = 0
			}
			w.mu.Unlock()
			// Some platforms emit Create immediately followed by Write; on
			// others (notably tests using O_CREATE|O_WRONLY+Write) the only
			// signal is Create. Tail eagerly so the very first line is not
			// stranded behind the next Write event.
			w.tailFile(event.Name, sink)
		}
	}
}

// tailFile reads any new bytes appended to path since the last visit and
// dispatches every recognised line. The post-read seek captures the new
// offset under the same lock so two concurrent Write events cannot race
// to read identical bytes. Open/Stat failures are logged at debug and the
// file is left in its current offset state — fsnotify will fire again on
// the next write and we will retry then.
func (w *Watcher) tailFile(path string, sink Sink) {
	f, err := os.Open(path)
	if err != nil {
		w.logger.Debug("storage: open jsonl failed", "path", path, "err", err)
		return
	}
	defer func() { _ = f.Close() }()

	w.mu.Lock()
	offset := w.tailOffsets[path]
	w.mu.Unlock()

	if _, err := f.Seek(offset, io.SeekStart); err != nil {
		w.logger.Debug("storage: seek failed", "path", path, "offset", offset, "err", err)
		return
	}

	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, scannerInitialBufSize), scannerMaxBufSize)
	for scanner.Scan() {
		line := scanner.Bytes()
		// Copy the line — bufio.Scanner reuses the underlying buffer on
		// the next Scan(), and parser callbacks may retain references
		// (json.RawMessage in particular).
		raw := make([]byte, len(line))
		copy(raw, line)

		var head map[string]json.RawMessage
		if err := json.Unmarshal(raw, &head); err != nil {
			continue
		}
		var typ string
		if rawType, ok := head["type"]; ok {
			_ = json.Unmarshal(rawType, &typ)
		}
		if !interestedTypes[typ] {
			continue
		}
		w.dispatch(typ, raw, sink)
	}
	if err := scanner.Err(); err != nil {
		w.logger.Debug("storage: scanner error", "path", path, "err", err)
	}

	pos, err := f.Seek(0, io.SeekCurrent)
	if err != nil {
		w.logger.Debug("storage: tell failed", "path", path, "err", err)
		return
	}
	w.mu.Lock()
	w.tailOffsets[path] = pos
	w.mu.Unlock()
}

// dispatch routes one decoded line to the appropriate sink callback. The
// telemetry counter increments unconditionally per recognised type — it
// is a "frames received" gauge, not a "frames delivered" one, so a sink
// failure does not skew the count. Decode/sink errors are logged at
// debug only; see docs/11_Bridge_Spec.md §9 for why these are not noisy.
func (w *Watcher) dispatch(typ string, raw []byte, sink Sink) {
	telemetry.StorageWatcherEventsTotal.Add(typ, 1)

	switch typ {
	case "ai-title":
		ev, err := parseAITitle(raw)
		if err != nil {
			w.logger.Debug("storage: ai-title decode failed", "err", err)
			return
		}
		if err := sink.OnAITitle(ev); err != nil {
			w.logger.Debug("storage: sink OnAITitle failed", "err", err)
		}
	case "pr-link":
		ev, err := parsePRLink(raw)
		if err != nil {
			w.logger.Debug("storage: pr-link decode failed", "err", err)
			return
		}
		if err := sink.OnPRLink(ev); err != nil {
			w.logger.Debug("storage: sink OnPRLink failed", "err", err)
		}
	case "attachment":
		ev, ok, err := parseHookAttachment(raw)
		if err != nil {
			w.logger.Debug("storage: attachment decode failed", "err", err)
			return
		}
		if !ok {
			return
		}
		if err := sink.OnHookAttachment(ev); err != nil {
			w.logger.Debug("storage: sink OnHookAttachment failed", "err", err)
		}
	}
}
