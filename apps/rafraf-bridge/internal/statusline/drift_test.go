package statusline_test

import (
	"bytes"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"testing"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/statusline"
)

// TestStatuslinePyMatchesDocReference asserts byte-equivalence between
// the embedded statusline.py and the canonical reference in
// docs/claude-code-usage-tracking.md. If this test fails, either:
//  1. Update docs/claude-code-usage-tracking.md to match the embedded asset, OR
//  2. Update assets/statusline.py to match the doc.
//
// Either way, both must stay in sync per the T0.5.9 contract: the doc
// is the canonical reference, the embed is the shipped artifact, and
// they must not drift silently.
func TestStatuslinePyMatchesDocReference(t *testing.T) {
	t.Parallel()

	// Locate doc relative to this test file: walk up from
	// apps/rafraf-bridge/internal/statusline/ to repo root, then
	// down into docs/.
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed — cannot locate test file path")
	}
	docPath := filepath.Join(
		filepath.Dir(thisFile),
		"..", "..", "..", "..",
		"docs", "claude-code-usage-tracking.md",
	)

	docBytes, err := os.ReadFile(docPath)
	if err != nil {
		t.Fatalf("read doc %q: %v", docPath, err)
	}

	// Extract first ```python ... ``` fenced code block from the doc.
	re := regexp.MustCompile("(?s)```python\\n(.*?)```")
	matches := re.FindSubmatch(docBytes)
	if len(matches) < 2 {
		t.Fatalf("no python code block found in %q", docPath)
	}
	docPython := matches[1]

	if !bytes.Equal(docPython, statusline.StatuslinePy) {
		t.Errorf(
			"statusline.py drift detected — doc reference and embedded asset diverged.\n"+
				"\nDoc reference (%d bytes) from %s:\n%s\n"+
				"\nEmbedded asset (%d bytes) from assets/statusline.py:\n%s\n"+
				"\nResolve by updating either the doc or the asset so they match byte-for-byte.",
			len(docPython), docPath, docPython,
			len(statusline.StatuslinePy), statusline.StatuslinePy,
		)
	}
}
