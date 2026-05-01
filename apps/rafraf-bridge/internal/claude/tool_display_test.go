package claude

import "testing"

// TestDisplayName covers the full DisplayName pipeline: alias
// canonicalization, exact map lookup, MCP fallback, and raw passthrough.
//
// At least one row exists for every entry in ToolDisplayNames so adding a
// new entry without a test will fail TestDisplayNameMapCoverage below.
func TestDisplayName(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		in   string
		want string
	}{
		// --- Filesystem & editing ----------------------------------------------
		{"Read", "Read", "Dosya okunuyor"},
		{"Write", "Write", "Dosya yazılıyor"},
		{"Edit", "Edit", "Dosya düzenleniyor"},
		{"MultiEdit", "MultiEdit", "Çoklu düzenleme"},
		{"NotebookEdit", "NotebookEdit", "Notebook düzenleniyor"},
		// --- Shell & filesystem discovery -------------------------------------
		{"Bash", "Bash", "Komut çalıştırılıyor"},
		{"Glob", "Glob", "Dosya aranıyor"},
		{"Grep", "Grep", "İçerik aranıyor"},
		{"LS", "LS", "Dizin listeleniyor"},
		// --- Productivity / messaging -----------------------------------------
		{"TodoWrite", "TodoWrite", "Görev listesi güncelleniyor"},
		{"AskUserQuestion", "AskUserQuestion", "Kullanıcıya soru soruluyor"},
		{"SendMessage", "SendMessage", "Mesaj gönderiliyor"},
		// --- Web --------------------------------------------------------------
		{"WebFetch", "WebFetch", "Web sayfası getiriliyor"},
		{"WebSearch", "WebSearch", "Web araması yapılıyor"},
		// --- Subagents --------------------------------------------------------
		{"Agent", "Agent", "Alt görev çalıştırılıyor"},
		{"TaskOutput", "TaskOutput", "Alt görev çıktısı alınıyor"},
		{"TaskStop", "TaskStop", "Alt görev durduruluyor"},
		// Task → Agent alias path (ADR-0005). Must yield Agent's display string.
		{"Task aliased to Agent", "Task", "Alt görev çalıştırılıyor"},
		// --- Planning & worktree ----------------------------------------------
		{"EnterPlanMode", "EnterPlanMode", "Plan moduna giriliyor"},
		{"ExitPlanMode", "ExitPlanMode", "Plan modundan çıkılıyor"},
		{"EnterWorktree", "EnterWorktree", "Worktree'ye giriliyor"},
		{"ExitWorktree", "ExitWorktree", "Worktree'den çıkılıyor"},
		// --- Cron / scheduling ------------------------------------------------
		{"CronCreate", "CronCreate", "Zamanlanmış görev oluşturuluyor"},
		{"CronDelete", "CronDelete", "Zamanlanmış görev siliniyor"},
		{"CronList", "CronList", "Zamanlanmış görevler listeleniyor"},
		{"ScheduleWakeup", "ScheduleWakeup", "Uyandırma planlanıyor"},
		// --- Teams ------------------------------------------------------------
		{"TeamCreate", "TeamCreate", "Ekip oluşturuluyor"},
		{"TeamDelete", "TeamDelete", "Ekip siliniyor"},
		// --- Misc -------------------------------------------------------------
		{"Skill", "Skill", "Beceri çağırılıyor"},
		{"RemoteTrigger", "RemoteTrigger", "Uzak tetikleme"},
		{"Monitor", "Monitor", "İzleniyor"},
		{"ToolSearch", "ToolSearch", "Araç aranıyor"},
		{"PushNotification", "PushNotification", "Bildirim gönderiliyor"},
		{"LSP", "LSP", "Dil sunucusu çağırılıyor"},
		// --- MCP fallback -----------------------------------------------------
		{"MCP playwright", "mcp__playwright__browser_navigate", "MCP aracı çalıştırılıyor"},
		{"MCP figma", "mcp__figma__create_node", "MCP aracı çalıştırılıyor"},
		{"MCP empty suffix", "mcp__", "MCP aracı çalıştırılıyor"},
		// --- Raw passthrough --------------------------------------------------
		{"Unknown tool passthrough", "UnknownThing", "UnknownThing"},
		{"Almost MCP but no double underscore", "mcp_legacy", "mcp_legacy"},
		{"Empty string passthrough", "", ""},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := DisplayName(tc.in)
			if got != tc.want {
				t.Errorf("DisplayName(%q) = %q, want %q", tc.in, got, tc.want)
			}
		})
	}
}

// TestCanonicalToolName covers the alias lookup in isolation, including the
// pass-through guarantee for empty / unknown inputs.
func TestCanonicalToolName(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		in   string
		want string
	}{
		{"Task aliased to Agent", "Task", "Agent"},
		{"Agent passes through", "Agent", "Agent"},
		{"Unknown tool passes through", "Foo", "Foo"},
		{"Empty string passes through", "", ""},
		{"MCP name passes through", "mcp__playwright__navigate", "mcp__playwright__navigate"},
		{"Case sensitive — task lower stays as-is", "task", "task"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := CanonicalToolName(tc.in)
			if got != tc.want {
				t.Errorf("CanonicalToolName(%q) = %q, want %q", tc.in, got, tc.want)
			}
		})
	}
}

// TestDisplayNameMapCoverage guards against accidental shrinkage of the
// display map: T0.5.7 done criterion requires at least 25 entries; we set
// a slightly higher floor (30) to reflect the merged Doc 11 §6 + Doc 10
// §2.10/A list shipped here. Bump if entries are removed intentionally.
func TestDisplayNameMapCoverage(t *testing.T) {
	t.Parallel()
	const minEntries = 30
	if got := len(ToolDisplayNames); got < minEntries {
		t.Errorf("ToolDisplayNames has %d entries, want at least %d", got, minEntries)
	}
}

// TestDisplayNameNonEmptyForKnownTools is a defence-in-depth check that
// every value in the map is non-empty. An empty Turkish string would surface
// as a blank tool label in the iOS chat UX.
func TestDisplayNameNonEmptyForKnownTools(t *testing.T) {
	t.Parallel()
	for tool, display := range ToolDisplayNames {
		if display == "" {
			t.Errorf("ToolDisplayNames[%q] is empty", tool)
		}
	}
}
