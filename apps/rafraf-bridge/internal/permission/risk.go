// risk.go — bridge-authoritative tool risk classification + input
// preview truncation.
//
// AUTHORITY: Risk classification lives in the bridge (per design doc
// §6 Q4) because the bridge has direct access to cwd, the Bash
// whitelist (mirroring docs/08_Host_Agent_Specification.md §5.5
// Shell Runner) and the path comparisons needed to discriminate
// in-cwd writes from off-cwd writes. The backend MUST consume the
// "low"|"medium"|"high" string returned here verbatim and MUST NOT
// re-classify on its side — this isolates the policy in one place.
//
// CATALOGUE (per design doc §2.1.3):
//   - Read, Glob, Grep, LS, TodoWrite, NotebookEdit  → low
//   - Edit, Write within cwd                          → medium
//   - Edit, Write outside cwd                         → medium
//   - Bash whitelist hit                              → medium
//   - Bash off-whitelist                              → high
//   - WebFetch, WebSearch                             → high
//   - Unknown / MCP / plugin tools                    → high (deny-default)
//
// REASON STRINGS are short audit hints surfaced into the
// EventSessionPermissionRequest.Reason field; iOS may render them as
// secondary text underneath the tool name.

package permission

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"unicode/utf8"
)

// inputPreviewMaxBytes caps the rendered preview at 240 bytes to fit
// comfortably inside an iOS approval sheet without leaking large
// diffs or full file contents.
const inputPreviewMaxBytes = 240

// riskLow / riskMedium / riskHigh are the canonical risk strings.
const (
	riskLow    = "low"
	riskMedium = "medium"
	riskHigh   = "high"
)

// safeBashCommands lists Bash command prefixes the bridge treats as
// medium-risk (vs. off-whitelist high-risk). Mirrors the iOS
// ApprovalToolPolicy safeBashCommands set BUT can be wider on the
// bridge — server-side trust is broader than iOS-display-side trust.
//
// Per docs/08_Host_Agent_Specification.md §5.5 Shell Runner whitelist:
// ls, pwd, cat, which, echo, head, tail, wc, date, git status|log|diff
// (read-only), docker ps|logs (read-only), npm test|run lint
// (deterministic CI commands).
//
// Matching is by leading-token prefix, NOT by exact string — `git
// status -sb` matches `git status` etc. Whitespace is normalised to
// single spaces before comparison.
var safeBashCommands = []string{
	"ls",
	"pwd",
	"cat",
	"which",
	"echo",
	"head",
	"tail",
	"wc",
	"date",
	"git status",
	"git log",
	"git diff",
	"docker ps",
	"docker logs",
	"npm test",
	"npm run lint",
	"go test",
	"go vet",
	"go build",
}

// readOnlyTools is the set the spike + Doc 11 §6 lists as
// always-low-risk because they cannot mutate state.
var readOnlyTools = map[string]struct{}{
	"Read":         {},
	"Glob":         {},
	"Grep":         {},
	"LS":           {},
	"TodoWrite":    {},
	"NotebookEdit": {},
}

// writeTools is the set whose risk depends on whether the target path
// is inside the bridge's cwd.
var writeTools = map[string]struct{}{
	"Edit":               {},
	"Write":              {},
	"MultiEdit":          {},
	"NotebookEdit_Write": {}, // defensive — claude variants may add this
}

// highRiskTools is the explicit deny-default short list per the
// design doc table — anything not enumerated falls through to high
// because "unknown / MCP / plugin tools → high (deny-default)".
var highRiskTools = map[string]struct{}{
	"WebFetch":  {},
	"WebSearch": {},
}

// classifyRisk returns the risk tier + a short audit reason string
// for the supplied tool. cwd may be empty when getwd failed at broker
// startup — in that case write-tool classification falls back to
// "outside cwd" which is still medium (no escalation to high since
// off-cwd writes are common in monorepos per the design table).
func classifyRisk(toolName string, toolInput json.RawMessage, cwd string) (string, string) {
	if _, ok := readOnlyTools[toolName]; ok {
		return riskLow, "read-only tool"
	}
	if _, ok := writeTools[toolName]; ok {
		path := extractStringField(toolInput, "file_path", "path", "filepath")
		if path == "" {
			// No path in the payload — treat as off-cwd write
			// (still medium per the table).
			return riskMedium, "write tool, path missing"
		}
		if isInsideCWD(path, cwd) {
			return riskMedium, "write within cwd"
		}
		return riskMedium, "write outside cwd"
	}
	if toolName == "Bash" {
		cmd := extractStringField(toolInput, "command", "cmd")
		if cmd == "" {
			return riskHigh, "bash with empty command"
		}
		if matchesBashWhitelist(cmd) {
			return riskMedium, "bash whitelist hit"
		}
		return riskHigh, "bash off-whitelist"
	}
	if _, ok := highRiskTools[toolName]; ok {
		return riskHigh, "network tool"
	}
	// Unknown / MCP / plugin / future tools → deny-default per
	// design doc §2.1.3 risk table.
	return riskHigh, "unknown tool (deny-default)"
}

// inputPreview returns a UTF-8-safe truncation of the JSON-marshalled
// tool_input to <= inputPreviewMaxBytes bytes. Truncation is at a
// rune boundary so the iOS decoder never sees an invalid UTF-8 chunk.
func inputPreview(toolInput json.RawMessage) string {
	if len(toolInput) == 0 {
		return ""
	}
	s := string(toolInput)
	if len(s) <= inputPreviewMaxBytes {
		return s
	}
	// Walk back from the byte budget to a rune boundary. utf8 encodes
	// up to 4 bytes per rune so we never need to walk more than 3
	// bytes back.
	cut := inputPreviewMaxBytes
	for cut > 0 && !utf8.RuneStart(s[cut]) {
		cut--
	}
	return s[:cut] + "..."
}

// extractStringField looks up the first matching JSON string field
// from toolInput. Returns "" when missing or the value is not a
// string. Uses RawMessage indirection so we don't pay the cost of
// fully decoding into map[string]any.
func extractStringField(toolInput json.RawMessage, candidates ...string) string {
	if len(toolInput) == 0 {
		return ""
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(toolInput, &fields); err != nil {
		return ""
	}
	for _, key := range candidates {
		raw, ok := fields[key]
		if !ok {
			continue
		}
		var val string
		if err := json.Unmarshal(raw, &val); err != nil {
			continue
		}
		return val
	}
	return ""
}

// isInsideCWD reports whether path resolves to a location inside cwd.
// Both inputs are cleaned + made absolute when possible. When cwd is
// empty we cannot meaningfully classify so we conservatively return
// false (forcing the "outside cwd" branch which is still medium).
func isInsideCWD(path, cwd string) bool {
	if cwd == "" || path == "" {
		return false
	}
	absPath := path
	if !filepath.IsAbs(absPath) {
		absPath = filepath.Join(cwd, absPath)
	}
	absPath = filepath.Clean(absPath)
	cwdClean := filepath.Clean(cwd)
	if absPath == cwdClean {
		return true
	}
	rel, err := filepath.Rel(cwdClean, absPath)
	if err != nil {
		return false
	}
	// rel == ".." or "../foo" means outside; "foo/bar" means inside.
	if strings.HasPrefix(rel, "..") {
		return false
	}
	return true
}

// matchesBashWhitelist normalises the leading tokens of cmd and
// reports whether any safeBashCommands entry is a token-prefix match.
// Both sides are lowercased — the whitelist uses canonical lowercase
// command names so case-only typos don't leak past.
func matchesBashWhitelist(cmd string) bool {
	norm := strings.ToLower(strings.TrimSpace(cmd))
	if norm == "" {
		return false
	}
	// Collapse internal whitespace to single spaces so e.g.
	// "git\tstatus" matches "git status".
	norm = strings.Join(strings.Fields(norm), " ")
	for _, allowed := range safeBashCommands {
		if norm == allowed {
			return true
		}
		if strings.HasPrefix(norm, allowed+" ") {
			return true
		}
	}
	return false
}
