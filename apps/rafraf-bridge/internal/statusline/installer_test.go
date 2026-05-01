package statusline_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/statusline"
)

// readSettings is a tiny helper duplicated here (rather than exported
// from the production package) so the test exercises the on-disk
// shape just like Claude Code itself would.
func readSettings(t *testing.T, path string) map[string]interface{} {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %q: %v", path, err)
	}
	out := map[string]interface{}{}
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatalf("decode %q: %v", path, err)
	}
	return out
}

func TestInstaller_FreshInstall(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()

	if err := statusline.InstallStatuslineScript(dir); err != nil {
		t.Fatalf("InstallStatuslineScript: %v", err)
	}

	scriptPath := filepath.Join(dir, "statusline.py")
	info, err := os.Stat(scriptPath)
	if err != nil {
		t.Fatalf("stat statusline.py: %v", err)
	}
	if !info.Mode().IsRegular() {
		t.Errorf("statusline.py is not a regular file")
	}
	// Skip exec-bit check on platforms where it is meaningless.
	if runtime.GOOS != "windows" && info.Mode().Perm()&0o100 == 0 {
		t.Errorf("statusline.py mode = %v, want exec bit set", info.Mode().Perm())
	}

	body, err := os.ReadFile(scriptPath)
	if err != nil {
		t.Fatalf("read statusline.py: %v", err)
	}
	if len(body) == 0 {
		t.Fatal("statusline.py is empty")
	}
	if string(body[:2]) != "#!" {
		t.Errorf("statusline.py missing shebang, first bytes: %q", body[:min(8, len(body))])
	}

	settings := readSettings(t, filepath.Join(dir, "settings.json"))
	sl, ok := settings["statusLine"].(map[string]interface{})
	if !ok {
		t.Fatalf("statusLine entry missing or wrong shape: %#v", settings["statusLine"])
	}
	if sl["type"] != "command" {
		t.Errorf("statusLine.type = %v, want \"command\"", sl["type"])
	}
	if sl["command"] != scriptPath {
		t.Errorf("statusLine.command = %v, want %q", sl["command"], scriptPath)
	}
}

func TestInstaller_PreservesCustomStatusLine(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()

	// Pre-seed settings.json with a custom statusLine plus a
	// sibling key. The installer must touch neither.
	custom := map[string]interface{}{
		"statusLine": map[string]interface{}{
			"type":    "command",
			"command": "/tmp/my-custom-statusline.sh",
		},
		"theme": "monokai",
	}
	raw, err := json.MarshalIndent(custom, "", "  ")
	if err != nil {
		t.Fatalf("marshal custom: %v", err)
	}
	settingsPath := filepath.Join(dir, "settings.json")
	if err := os.WriteFile(settingsPath, raw, 0o644); err != nil {
		t.Fatalf("seed settings.json: %v", err)
	}

	if err := statusline.InstallStatuslineScript(dir); err != nil {
		t.Fatalf("InstallStatuslineScript: %v", err)
	}

	got := readSettings(t, settingsPath)
	sl, ok := got["statusLine"].(map[string]interface{})
	if !ok {
		t.Fatalf("statusLine missing/wrong shape: %#v", got["statusLine"])
	}
	if sl["command"] != "/tmp/my-custom-statusline.sh" {
		t.Errorf("custom statusLine.command clobbered: got %v", sl["command"])
	}
	if got["theme"] != "monokai" {
		t.Errorf("sibling key 'theme' lost: got %v", got["theme"])
	}

	// statusline.py itself MUST still be written even when settings
	// are left alone — the operator may want to opt in manually.
	if _, err := os.Stat(filepath.Join(dir, "statusline.py")); err != nil {
		t.Errorf("statusline.py missing after install with custom config: %v", err)
	}
}

func TestInstaller_PreservesSiblingKeysOnFreshPatch(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()

	// settings.json exists but has no statusLine key — installer
	// must add ours while preserving the existing siblings.
	pre := map[string]interface{}{
		"theme":     "ayu",
		"verbosity": float64(2),
	}
	raw, err := json.MarshalIndent(pre, "", "  ")
	if err != nil {
		t.Fatalf("marshal pre: %v", err)
	}
	settingsPath := filepath.Join(dir, "settings.json")
	if err := os.WriteFile(settingsPath, raw, 0o644); err != nil {
		t.Fatalf("seed settings.json: %v", err)
	}

	if err := statusline.InstallStatuslineScript(dir); err != nil {
		t.Fatalf("InstallStatuslineScript: %v", err)
	}

	got := readSettings(t, settingsPath)
	if got["theme"] != "ayu" {
		t.Errorf("theme lost: %v", got["theme"])
	}
	if got["verbosity"] != float64(2) {
		t.Errorf("verbosity lost: %v", got["verbosity"])
	}
	if _, ok := got["statusLine"].(map[string]interface{}); !ok {
		t.Errorf("statusLine not added: %#v", got["statusLine"])
	}
}

func TestInstaller_Idempotent(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()

	if err := statusline.InstallStatuslineScript(dir); err != nil {
		t.Fatalf("first install: %v", err)
	}
	settingsPath := filepath.Join(dir, "settings.json")
	first, err := os.ReadFile(settingsPath)
	if err != nil {
		t.Fatalf("read settings after first install: %v", err)
	}

	// Second install: by step 3 of InstallStatuslineScript a
	// "statusLine" key already exists so settings.json must be
	// byte-identical afterwards. statusline.py is allowed to be
	// rewritten (idempotent in content).
	if err := statusline.InstallStatuslineScript(dir); err != nil {
		t.Fatalf("second install: %v", err)
	}
	second, err := os.ReadFile(settingsPath)
	if err != nil {
		t.Fatalf("read settings after second install: %v", err)
	}

	if string(first) != string(second) {
		t.Errorf("settings.json changed across idempotent re-install\nbefore:\n%s\nafter:\n%s", first, second)
	}
}

func TestInstaller_CreatesClaudeDirIfMissing(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	// Nested path that does not yet exist — installer must mkdir -p.
	dir := filepath.Join(root, "nested", "dot-claude")

	if err := statusline.InstallStatuslineScript(dir); err != nil {
		t.Fatalf("install into non-existent dir: %v", err)
	}
	if _, err := os.Stat(filepath.Join(dir, "statusline.py")); err != nil {
		t.Errorf("statusline.py not written into nested dir: %v", err)
	}
	if _, err := os.Stat(filepath.Join(dir, "settings.json")); err != nil {
		t.Errorf("settings.json not written into nested dir: %v", err)
	}
}

func TestInstaller_EmptyClaudeDirReturnsError(t *testing.T) {
	t.Parallel()
	if err := statusline.InstallStatuslineScript(""); err == nil {
		t.Fatal("expected error for empty claudeDir")
	}
}

func TestInstaller_HandlesEmptySettingsFile(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	settingsPath := filepath.Join(dir, "settings.json")
	if err := os.WriteFile(settingsPath, []byte{}, 0o644); err != nil {
		t.Fatalf("seed empty settings.json: %v", err)
	}

	if err := statusline.InstallStatuslineScript(dir); err != nil {
		t.Fatalf("install with empty settings.json: %v", err)
	}
	got := readSettings(t, settingsPath)
	if _, ok := got["statusLine"]; !ok {
		t.Errorf("statusLine not added to empty settings.json")
	}
}

func TestInstaller_StatuslinePyEmbedNonEmpty(t *testing.T) {
	t.Parallel()
	if len(statusline.StatuslinePy) == 0 {
		t.Fatal("StatuslinePy embed is empty — go:embed directive broken")
	}
	if string(statusline.StatuslinePy[:2]) != "#!" {
		t.Errorf("embedded statusline.py missing shebang")
	}
}
