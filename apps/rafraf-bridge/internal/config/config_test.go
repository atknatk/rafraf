package config

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// writeTempConfig writes body to a temp file under t.TempDir() and
// returns the absolute path. Any error fails the test fatally.
func writeTempConfig(t *testing.T, body string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "config.toml")
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatalf("write fixture: %v", err)
	}
	return path
}

// validTOML is a minimally-complete TOML body that passes validation;
// individual cases override fields via string substitution.
const validTOML = `
backend_url = "wss://api.rafraf.app/api/v1/agent/ws"
pairing_token = ""
api_token_path = "~/.config/rafraf-bridge/token"
bridge_id = ""

claude_binary = "claude"
project_dir = "~/Code"
permission_mode = "acceptEdits"
agent_teams = true

heartbeat_interval = "15s"
reconnect_initial = "500ms"
reconnect_max = "30s"

[storage_watcher]
enabled = true
projects_root = "~/.claude/projects"
max_file_age_days = 30

[statusline]
enabled = true
usage_path = "~/.claude/usage.json"
poll_every = "5s"
stale_after = "30m"

[telemetry]
expvar_enabled = true
expvar_addr = "127.0.0.1:9090"
log_level = "info"
log_file = "~/Library/Logs/rafraf-bridge/bridge.log"
`

func TestLoad(t *testing.T) {
	home, err := os.UserHomeDir()
	if err != nil {
		t.Fatalf("UserHomeDir: %v", err)
	}

	// Each case either sets `body` (writes a temp file) or sets
	// `path` directly to exercise filesystem-error branches.
	type testCase struct {
		name        string
		body        string
		path        string // used only when body == ""
		wantErr     bool
		errSubstrs  []string
		assertOnCfg func(t *testing.T, cfg *Config)
	}

	cases := []testCase{
		{
			name: "happy_path_valid_toml",
			body: validTOML,
			assertOnCfg: func(t *testing.T, cfg *Config) {
				if cfg.BackendURL != "wss://api.rafraf.app/api/v1/agent/ws" {
					t.Errorf("BackendURL = %q", cfg.BackendURL)
				}
				if cfg.HeartbeatInterval != 15*time.Second {
					t.Errorf("HeartbeatInterval = %s", cfg.HeartbeatInterval)
				}
				if cfg.PermissionMode != "acceptEdits" {
					t.Errorf("PermissionMode = %q", cfg.PermissionMode)
				}
			},
		},
		{
			name:       "missing_path",
			path:       "/nonexistent/definitely-not-here/config.toml",
			wantErr:    true,
			errSubstrs: []string{"config:", "read"},
		},
		{
			name:       "empty_path",
			path:       "",
			wantErr:    true,
			errSubstrs: []string{"config: empty path"},
		},
		{
			name:       "malformed_toml",
			body:       "this is = not = valid toml [[[",
			wantErr:    true,
			errSubstrs: []string{"config:", "parse"},
		},
		{
			name:       "invalid_scheme",
			body:       strings.Replace(validTOML, `"wss://api.rafraf.app/api/v1/agent/ws"`, `"http://example.com"`, 1),
			wantErr:    true,
			errSubstrs: []string{"backend_url must use ws:// or wss://"},
		},
		{
			name:       "missing_required_backend_url",
			body:       strings.Replace(validTOML, `"wss://api.rafraf.app/api/v1/agent/ws"`, `""`, 1),
			wantErr:    true,
			errSubstrs: []string{"backend_url is required"},
		},
		{
			name:       "bad_permission_mode",
			body:       strings.Replace(validTOML, `"acceptEdits"`, `"yolo"`, 1),
			wantErr:    true,
			errSubstrs: []string{"permission_mode must be one of: default, acceptEdits, bypassPermissions, plan"},
		},
		{
			name:       "negative_heartbeat",
			body:       strings.Replace(validTOML, `heartbeat_interval = "15s"`, `heartbeat_interval = "-1s"`, 1),
			wantErr:    true,
			errSubstrs: []string{"heartbeat_interval must be > 0"},
		},
		{
			name: "reconnect_max_less_than_initial",
			body: strings.NewReplacer(
				`reconnect_initial = "500ms"`, `reconnect_initial = "10s"`,
				`reconnect_max = "30s"`, `reconnect_max = "5s"`,
			).Replace(validTOML),
			wantErr:    true,
			errSubstrs: []string{"reconnect_max must be >= reconnect_initial"},
		},
		{
			name:       "bad_log_level",
			body:       strings.Replace(validTOML, `log_level = "info"`, `log_level = "trace"`, 1),
			wantErr:    true,
			errSubstrs: []string{"telemetry.log_level must be one of: debug, info, warn, error"},
		},
		{
			name: "multiple_errors_joined",
			body: strings.NewReplacer(
				`"wss://api.rafraf.app/api/v1/agent/ws"`, `""`,
				`"acceptEdits"`, `"yolo"`,
				`log_level = "info"`, `log_level = "trace"`,
			).Replace(validTOML),
			wantErr: true,
			errSubstrs: []string{
				"backend_url is required",
				"permission_mode must be one of: default, acceptEdits, bypassPermissions, plan",
				"telemetry.log_level must be one of: debug, info, warn, error",
			},
		},
		{
			name: "tilde_expansion",
			body: strings.Replace(validTOML, `project_dir = "~/Code"`, `project_dir = "~/Code"`, 1),
			assertOnCfg: func(t *testing.T, cfg *Config) {
				want := filepath.Join(home, "Code")
				if cfg.ProjectDir != want {
					t.Errorf("ProjectDir = %q want %q", cfg.ProjectDir, want)
				}
				wantProjects := filepath.Join(home, ".claude", "projects")
				if cfg.StorageWatcher.ProjectsRoot != wantProjects {
					t.Errorf("StorageWatcher.ProjectsRoot = %q want %q",
						cfg.StorageWatcher.ProjectsRoot, wantProjects)
				}
			},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			path := tc.path
			if tc.body != "" {
				path = writeTempConfig(t, tc.body)
			}

			cfg, err := Load(path)

			if tc.wantErr {
				if err == nil {
					t.Fatalf("Load() error = nil, want error containing %v", tc.errSubstrs)
				}
				msg := err.Error()
				for _, sub := range tc.errSubstrs {
					if !strings.Contains(msg, sub) {
						t.Errorf("error %q missing substring %q", msg, sub)
					}
				}
				return
			}

			if err != nil {
				t.Fatalf("Load() unexpected error: %v", err)
			}
			if cfg == nil {
				t.Fatal("Load() returned nil config without error")
			}
			if tc.assertOnCfg != nil {
				tc.assertOnCfg(t, cfg)
			}
		})
	}
}

func TestLoadDefault(t *testing.T) {
	cfg, err := LoadDefault()
	if err != nil {
		t.Fatalf("LoadDefault() error: %v", err)
	}
	if cfg == nil {
		t.Fatal("LoadDefault() returned nil config")
	}

	if cfg.BackendURL != "wss://api.rafraf.app/api/v1/agent/ws" {
		t.Errorf("BackendURL = %q want wss://api.rafraf.app/api/v1/agent/ws", cfg.BackendURL)
	}
	if cfg.HeartbeatInterval != 15*time.Second {
		t.Errorf("HeartbeatInterval = %s want 15s", cfg.HeartbeatInterval)
	}
	if cfg.ReconnectInitial != 500*time.Millisecond {
		t.Errorf("ReconnectInitial = %s want 500ms", cfg.ReconnectInitial)
	}
	if cfg.ReconnectMax != 30*time.Second {
		t.Errorf("ReconnectMax = %s want 30s", cfg.ReconnectMax)
	}
	if cfg.PermissionMode != "acceptEdits" {
		t.Errorf("PermissionMode = %q want acceptEdits", cfg.PermissionMode)
	}
	if cfg.Telemetry.LogLevel != "info" {
		t.Errorf("Telemetry.LogLevel = %q want info", cfg.Telemetry.LogLevel)
	}
	if cfg.Statusline.PollEvery != 5*time.Second {
		t.Errorf("Statusline.PollEvery = %s want 5s", cfg.Statusline.PollEvery)
	}
	if cfg.StorageWatcher.MaxFileAgeDays != 30 {
		t.Errorf("StorageWatcher.MaxFileAgeDays = %d want 30", cfg.StorageWatcher.MaxFileAgeDays)
	}
}

// TestMultiErrorJoinUnwraps confirms that the joined validation error
// genuinely wraps each individual error (so callers can still
// errors.Is / errors.As against specific sentinel errors in the
// future). For now we just assert the error count via Unwrap()[]error.
func TestMultiErrorJoinUnwraps(t *testing.T) {
	body := strings.NewReplacer(
		`"wss://api.rafraf.app/api/v1/agent/ws"`, `""`,
		`"acceptEdits"`, `"yolo"`,
		`log_level = "info"`, `log_level = "trace"`,
	).Replace(validTOML)
	path := writeTempConfig(t, body)

	_, err := Load(path)
	if err == nil {
		t.Fatal("expected error")
	}

	type unwrapper interface{ Unwrap() []error }
	var u unwrapper
	if !errors.As(err, &u) {
		t.Fatalf("error %T does not implement Unwrap() []error; cannot verify join", err)
	}
	parts := u.Unwrap()
	if len(parts) < 3 {
		t.Errorf("Unwrap() returned %d errors, want >=3", len(parts))
	}
}

// Sanity check that errors.Is on a wrapped read failure still surfaces
// the underlying os error type — useful for future callers.
func TestLoadMissingPathWrapsOSError(t *testing.T) {
	_, err := Load("/nonexistent/definitely-not-here/config.toml")
	if err == nil {
		t.Fatal("expected error")
	}
	if !errors.Is(err, os.ErrNotExist) {
		t.Errorf("error %v does not wrap os.ErrNotExist", err)
	}
}
