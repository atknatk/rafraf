// Package config defines the rafraf-bridge daemon configuration loaded
// from a TOML file at ~/.config/rafraf-bridge/config.toml (or any path
// supplied via CLI flag in T0.5.4+).
//
// The struct contract follows docs/11_Bridge_Spec.md §3.1 and the
// embedded default_config.toml mirrors §12.1 verbatim. Load() applies
// duration/string defaults, expands tilde-prefixed paths to $HOME and
// then runs Validate(); validation failures are aggregated via
// errors.Join so a single pass surfaces all issues.
package config

import (
	_ "embed"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/BurntSushi/toml"
)

// DefaultConfigTOML is the verbatim contents of default_config.toml,
// embedded at build time so the bridge can fall back to a sane example
// (and tests can exercise the defaults pipeline) without touching the
// filesystem.
//
//go:embed default_config.toml
var DefaultConfigTOML []byte

// Config mirrors docs/11_Bridge_Spec.md §3.1.
type Config struct {
	BackendURL   string `toml:"backend_url"`
	PairingToken string `toml:"pairing_token"`
	BridgeID     string `toml:"bridge_id"`
	APITokenPath string `toml:"api_token_path"`

	ClaudeBinary   string `toml:"claude_binary"`
	ProjectDir     string `toml:"project_dir"`
	PermissionMode string `toml:"permission_mode"`
	AgentTeams     bool   `toml:"agent_teams"`

	HeartbeatInterval time.Duration `toml:"heartbeat_interval"`
	ReconnectInitial  time.Duration `toml:"reconnect_initial"`
	ReconnectMax      time.Duration `toml:"reconnect_max"`

	// PermissionTimeout caps how long the bridge's PreToolUse broker
	// waits on the iOS user's approval before the broker self-denies
	// (DecisionExpired → hook reply "block"). The same value is
	// stamped onto the outbound permission_request envelope's
	// timeout_ms field so iOS RFApprovalSheet's countdown + backend
	// ApprovalService's clamp track it end-to-end.
	//
	// Default: 180s (mirrors the backend's per-category default in
	// apps/backend/app/services/approval_service.py). Validation
	// rejects values <= 0 or > 600s.
	PermissionTimeout time.Duration `toml:"permission_timeout"`

	StorageWatcher StorageWatcherConfig `toml:"storage_watcher"`
	Statusline     StatuslineConfig     `toml:"statusline"`
	Telemetry      TelemetryConfig      `toml:"telemetry"`
}

// DefaultPermissionTimeout is the broker's per-request approval
// ceiling when the operator does not set permission_timeout in
// config.toml. Mirrors permission.defaultRequestTimeout in the
// broker package and is duplicated here so the config layer has a
// stable, importable default without taking a dep on the permission
// package (avoids an import cycle).
const DefaultPermissionTimeout = 180 * time.Second

// MaxPermissionTimeout is the upper bound enforced by Validate. The
// 590s ceiling is calibrated against claude CLI's 600s tool-hook
// execution cap (per ~/.claude/cache/changelog.md "Changed tool hook
// execution timeout from 60 seconds to 10 minutes"): the runner
// stamps `cfg.PermissionTimeout + 10s grace` into the per-session
// settings overlay's `timeout` field, so capping config at 590s keeps
// the overlay value at-or-under claude's hard 600s limit. Without
// this margin a `permission_timeout = "600s"` would silently produce
// an overlay timeout of 610s that claude CLI would clamp at 600s,
// drifting the layer out of lockstep.
const MaxPermissionTimeout = 590 * time.Second

// StorageWatcherConfig configures the ~/.claude/projects/ JSONL watcher.
type StorageWatcherConfig struct {
	Enabled        bool   `toml:"enabled"`
	ProjectsRoot   string `toml:"projects_root"`
	MaxFileAgeDays int    `toml:"max_file_age_days"`
}

// StatuslineConfig configures the ~/.claude/usage.json poller.
type StatuslineConfig struct {
	Enabled    bool          `toml:"enabled"`
	UsagePath  string        `toml:"usage_path"`
	PollEvery  time.Duration `toml:"poll_every"`
	StaleAfter time.Duration `toml:"stale_after"`
}

// TelemetryConfig configures structured logging and the expvar HTTP
// surface (T0.5.11 will wire the logger to LogLevel/LogFile).
type TelemetryConfig struct {
	ExpvarEnabled bool   `toml:"expvar_enabled"`
	ExpvarAddr    string `toml:"expvar_addr"`
	LogLevel      string `toml:"log_level"`
	LogFile       string `toml:"log_file"`
}

// validPermissionModes is the closed set accepted by `claude --permission-mode`.
var validPermissionModes = map[string]struct{}{
	"default":           {},
	"acceptEdits":       {},
	"bypassPermissions": {},
	"plan":              {},
}

// validLogLevels matches log/slog level names we expose to operators.
var validLogLevels = map[string]struct{}{
	"debug": {},
	"info":  {},
	"warn":  {},
	"error": {},
}

// Load reads, decodes and validates a config TOML at the given path.
// A leading "~" in path is expanded to the user's home directory before
// reading. Path-shaped string fields inside the resulting Config are
// also tilde-expanded, then sensible defaults are applied for any
// unset duration/string fields, and finally Validate() is invoked. The
// returned error from Validate() (which itself may wrap multiple
// errors via errors.Join) is propagated as-is.
func Load(path string) (*Config, error) {
	if path == "" {
		return nil, errors.New("config: empty path")
	}

	expanded, err := expandHome(path)
	if err != nil {
		return nil, fmt.Errorf("config: expand path: %w", err)
	}

	data, err := os.ReadFile(expanded)
	if err != nil {
		return nil, fmt.Errorf("config: read %q: %w", expanded, err)
	}

	cfg := &Config{}
	if _, err := toml.Decode(string(data), cfg); err != nil {
		return nil, fmt.Errorf("config: parse %q: %w", expanded, err)
	}

	if err := cfg.applyDefaults(); err != nil {
		return nil, fmt.Errorf("config: apply defaults: %w", err)
	}

	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	return cfg, nil
}

// LoadDefault decodes the embedded default_config.toml, applies
// defaults, validates and returns the resulting Config. It is useful
// for tests and for documenting the expected baseline shape.
func LoadDefault() (*Config, error) {
	cfg := &Config{}
	if _, err := toml.Decode(string(DefaultConfigTOML), cfg); err != nil {
		return nil, fmt.Errorf("config: parse embedded default: %w", err)
	}
	if err := cfg.applyDefaults(); err != nil {
		return nil, fmt.Errorf("config: apply defaults: %w", err)
	}
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	return cfg, nil
}

// applyDefaults fills in zero-valued fields with the documented
// defaults and tilde-expands path-shaped strings. Called by Load and
// LoadDefault before Validate.
func (c *Config) applyDefaults() error {
	if c.ClaudeBinary == "" {
		c.ClaudeBinary = "claude"
	}
	if c.PermissionMode == "" {
		c.PermissionMode = "acceptEdits"
	}

	if c.HeartbeatInterval == 0 {
		c.HeartbeatInterval = 15 * time.Second
	}
	if c.ReconnectInitial == 0 {
		c.ReconnectInitial = 500 * time.Millisecond
	}
	if c.ReconnectMax == 0 {
		c.ReconnectMax = 30 * time.Second
	}
	if c.PermissionTimeout == 0 {
		c.PermissionTimeout = DefaultPermissionTimeout
	}

	if c.StorageWatcher.MaxFileAgeDays == 0 {
		c.StorageWatcher.MaxFileAgeDays = 30
	}
	if c.StorageWatcher.ProjectsRoot == "" {
		c.StorageWatcher.ProjectsRoot = "~/.claude/projects"
	}

	if c.Statusline.UsagePath == "" {
		c.Statusline.UsagePath = "~/.claude/usage.json"
	}
	if c.Statusline.PollEvery == 0 {
		c.Statusline.PollEvery = 5 * time.Second
	}
	if c.Statusline.StaleAfter == 0 {
		c.Statusline.StaleAfter = 30 * time.Minute
	}

	if c.Telemetry.ExpvarAddr == "" {
		c.Telemetry.ExpvarAddr = "127.0.0.1:9090"
	}
	if c.Telemetry.LogLevel == "" {
		c.Telemetry.LogLevel = "info"
	}

	// Tilde-expand the path-shaped fields after defaults are in place
	// so default values like "~/.claude/projects" also get resolved.
	expansions := []*string{
		&c.APITokenPath,
		&c.ProjectDir,
		&c.StorageWatcher.ProjectsRoot,
		&c.Statusline.UsagePath,
		&c.Telemetry.LogFile,
	}
	for _, fieldPtr := range expansions {
		if *fieldPtr == "" {
			continue
		}
		expanded, err := expandHome(*fieldPtr)
		if err != nil {
			return err
		}
		*fieldPtr = expanded
	}
	return nil
}

// Validate enforces the invariants documented in
// docs/11_Bridge_Spec.md §3.1 / §12. Multiple violations are returned
// as a single joined error.
func (c *Config) Validate() error {
	var errs []error

	switch {
	case c.BackendURL == "":
		errs = append(errs, errors.New("config: backend_url is required"))
	case !strings.HasPrefix(c.BackendURL, "ws://") && !strings.HasPrefix(c.BackendURL, "wss://"):
		errs = append(errs, fmt.Errorf("config: backend_url must use ws:// or wss:// scheme (got %q)", c.BackendURL))
	}

	if _, ok := validPermissionModes[c.PermissionMode]; !ok {
		errs = append(errs, fmt.Errorf(
			"config: permission_mode must be one of: default, acceptEdits, bypassPermissions, plan (got %q)",
			c.PermissionMode,
		))
	}

	if c.HeartbeatInterval <= 0 {
		errs = append(errs, fmt.Errorf("config: heartbeat_interval must be > 0 (got %s)", c.HeartbeatInterval))
	}
	if c.ReconnectInitial <= 0 {
		errs = append(errs, fmt.Errorf("config: reconnect_initial must be > 0 (got %s)", c.ReconnectInitial))
	}
	if c.ReconnectMax < c.ReconnectInitial {
		errs = append(errs, fmt.Errorf(
			"config: reconnect_max must be >= reconnect_initial (max=%s initial=%s)",
			c.ReconnectMax, c.ReconnectInitial,
		))
	}

	if c.PermissionTimeout <= 0 {
		errs = append(errs, fmt.Errorf(
			"config: permission_timeout must be > 0 (got %s)",
			c.PermissionTimeout,
		))
	}
	if c.PermissionTimeout > MaxPermissionTimeout {
		errs = append(errs, fmt.Errorf(
			"config: permission_timeout must be <= %s (got %s)",
			MaxPermissionTimeout, c.PermissionTimeout,
		))
	}

	if c.StorageWatcher.MaxFileAgeDays < 0 {
		errs = append(errs, fmt.Errorf(
			"config: storage_watcher.max_file_age_days must be >= 0 (got %d)",
			c.StorageWatcher.MaxFileAgeDays,
		))
	}
	if c.Statusline.PollEvery <= 0 {
		errs = append(errs, fmt.Errorf(
			"config: statusline.poll_every must be > 0 (got %s)",
			c.Statusline.PollEvery,
		))
	}

	if _, ok := validLogLevels[c.Telemetry.LogLevel]; !ok {
		errs = append(errs, fmt.Errorf(
			"config: telemetry.log_level must be one of: debug, info, warn, error (got %q)",
			c.Telemetry.LogLevel,
		))
	}

	return errors.Join(errs...)
}

// expandHome resolves a leading "~" or "~/" in s to the current user's
// home directory. Other inputs are returned unchanged. A bare "~" maps
// to $HOME and "~/foo/bar" maps to "$HOME/foo/bar".
func expandHome(s string) (string, error) {
	if s == "" || s[0] != '~' {
		return s, nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("expand home: %w", err)
	}
	if s == "~" {
		return home, nil
	}
	if strings.HasPrefix(s, "~/") {
		return filepath.Join(home, s[2:]), nil
	}
	// "~user/..." form is not supported; leave it as-is.
	return s, nil
}
