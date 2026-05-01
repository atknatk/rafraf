// Package claude — tool name aliasing.
//
// See ADR-0005 (docs/adr/0005-tool-name-aliasing-task-agent.md) for the full
// rationale. Summary: claude CLI v2.x lists "Task" in the system/init tools[]
// payload but always emits "Agent" in assistant content tool_use.name. The
// bridge canonicalizes to "Agent" so downstream code (display lookup, state
// tracking, iOS WebSocket message types) only ever sees one name per tool.
//
// Future Anthropic CLI versions may rename or sync the alias — when this
// happens, only this map needs updating.

package claude

// toolAliases maps Anthropic CLI's internal/legacy tool names to canonical
// names used everywhere else in the bridge.
//
// Per ADR-0005 the only known alias today is Task → Agent. Add new entries
// here when empirical session sampling reveals additional drift.
var toolAliases = map[string]string{
	"Task": "Agent",
}

// CanonicalToolName returns the canonical (post-alias) tool name. Names that
// are not in the alias map (including the empty string) pass through
// unchanged so callers can rely on a non-panicking, total function.
func CanonicalToolName(name string) string {
	if alias, ok := toolAliases[name]; ok {
		return alias
	}
	return name
}
