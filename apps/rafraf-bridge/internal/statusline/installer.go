package statusline

import (
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
)

// StatuslinePy is the verbatim Python script body that Claude Code
// invokes on every interactive statusline render. It is embedded into
// the Go binary so that InstallStatuslineScript can deploy it to
// ~/.claude/ without any external file dependency at runtime.
//
// The script writes a small JSON file at ~/.claude/usage.json which
// the Watcher (watcher.go) polls. Source / rationale lives in
// docs/11_Bridge_Spec.md §8 and docs/claude-code-usage-tracking.md.
//
//go:embed assets/statusline.py
var StatuslinePy []byte

// statuslineFileMode is the permission bitmask for the deployed
// statusline.py — must include the user execute bit because Claude
// Code spawns the script directly (no `python3 …` indirection).
const statuslineFileMode = 0o755

// settingsFileMode is the permission bitmask for the patched
// settings.json. Matches the mode Claude Code itself writes; we are
// careful never to widen permissions on an existing file (see below).
const settingsFileMode = 0o644

// statusLineKey is the top-level key inside ~/.claude/settings.json
// that Claude Code reads to discover an external statusline command.
// Claude Code's schema documents the value as `{"type": "command",
// "command": "<path>"}`.
const statusLineKey = "statusLine"

// InstallStatuslineScript writes the embedded statusline.py into
// claudeDir and merge-safely registers it in claudeDir/settings.json.
//
// Behaviour:
//
//  1. Ensure claudeDir exists (create with 0o755 if missing). The
//     standard layout is ~/.claude — Claude Code itself creates it on
//     first launch, but the bridge installer must not assume the
//     user has run claude even once.
//
//  2. Write the embedded statusline.py to claudeDir/statusline.py
//     with mode 0o755. This always overwrites — script body changes
//     ride along with bridge releases and operators expect the new
//     copy after `brew upgrade rafraf-bridge` / pkg reinstall.
//
//  3. Read claudeDir/settings.json (treat ENOENT as an empty map).
//     If a "statusLine" key already exists we leave the document
//     untouched and return nil — the user has explicitly customised
//     their statusline and we never clobber that. Otherwise insert
//     the canonical {"type": "command", "command": <abs path>} entry,
//     then atomically rewrite the file at mode 0o644. All sibling
//     keys are preserved.
//
// Filesystem failures are surfaced via wrapped errors. Callers should
// log and continue — the bridge's core forwarding loop runs fine
// without the statusline pipeline (the Watcher will quietly never see
// usage.json appear).
func InstallStatuslineScript(claudeDir string) error {
	if claudeDir == "" {
		return errors.New("statusline: empty claudeDir")
	}

	if err := os.MkdirAll(claudeDir, 0o755); err != nil {
		return fmt.Errorf("statusline: create claude dir %q: %w", claudeDir, err)
	}

	target := filepath.Join(claudeDir, "statusline.py")
	if err := os.WriteFile(target, StatuslinePy, statuslineFileMode); err != nil {
		return fmt.Errorf("statusline: write %q: %w", target, err)
	}
	// Re-chmod explicitly: WriteFile honours umask on existing files,
	// so a previous 0o600 install can survive a re-run with the same
	// (now incorrect) mode unless we force it back.
	if err := os.Chmod(target, statuslineFileMode); err != nil {
		return fmt.Errorf("statusline: chmod %q: %w", target, err)
	}

	settingsPath := filepath.Join(claudeDir, "settings.json")
	settings, err := readSettings(settingsPath)
	if err != nil {
		return fmt.Errorf("statusline: read %q: %w", settingsPath, err)
	}

	if _, hasCustom := settings[statusLineKey]; hasCustom {
		// Operator already configured a custom statusline command —
		// leave their config untouched. The script we wrote in step
		// 2 still sits at claudeDir/statusline.py for them to opt
		// into manually if they want.
		return nil
	}

	settings[statusLineKey] = map[string]string{
		"type":    "command",
		"command": target,
	}

	if err := writeSettings(settingsPath, settings); err != nil {
		return fmt.Errorf("statusline: write %q: %w", settingsPath, err)
	}
	return nil
}

// readSettings loads claudeDir/settings.json into a generic map. A
// missing file is treated as an empty document; any other I/O or JSON
// error is propagated. The decoded map preserves user keys as
// json.Number-free generic interface{} values so writeSettings can
// round-trip them without coercion.
func readSettings(path string) (map[string]interface{}, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return map[string]interface{}{}, nil
		}
		return nil, err
	}
	if len(raw) == 0 {
		return map[string]interface{}{}, nil
	}
	out := map[string]interface{}{}
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, fmt.Errorf("decode json: %w", err)
	}
	return out, nil
}

// writeSettings serialises m to JSON (two-space indent, deterministic
// thanks to encoding/json's lexicographic key sort) and writes it to
// path with settingsFileMode. The write goes through a temp file +
// rename so a crash mid-write cannot leave Claude Code with a
// truncated settings.json — that file is critical to the user's CLI
// configuration and must never appear corrupt on disk.
func writeSettings(path string, m map[string]interface{}) error {
	body, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
		return fmt.Errorf("encode json: %w", err)
	}
	// Trailing newline keeps the file POSIX-clean and matches the
	// convention used by the rest of the Claude Code config tree.
	body = append(body, '\n')

	dir := filepath.Dir(path)
	tmp, err := os.CreateTemp(dir, "settings.json.*.tmp")
	if err != nil {
		return fmt.Errorf("create temp: %w", err)
	}
	tmpPath := tmp.Name()
	// Best-effort cleanup if any later step fails; nil-effect on the
	// happy path because the Rename below makes tmpPath disappear.
	defer func() { _ = os.Remove(tmpPath) }()

	if _, err := tmp.Write(body); err != nil {
		_ = tmp.Close()
		return fmt.Errorf("write temp: %w", err)
	}
	if err := tmp.Chmod(settingsFileMode); err != nil {
		_ = tmp.Close()
		return fmt.Errorf("chmod temp: %w", err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("close temp: %w", err)
	}
	if err := os.Rename(tmpPath, path); err != nil {
		return fmt.Errorf("rename temp: %w", err)
	}
	return nil
}
