# RafRaf -- Pipeline Commands Reference

This guide documents the slash commands available for the AI-driven development pipeline.

---

## /pipeline-run

Run the full CI pipeline for the current branch.

```
/pipeline-run [--layer backend|ios|agent] [--skip-lint] [--skip-test]
```

**Steps executed:**
1. Lint (ruff check + mypy for Python, swiftlint for Swift)
2. Test (pytest / xcodebuild test)
3. Build (pip install / xcodebuild build)
4. Coverage check (fail if below threshold)

**Examples:**
```
/pipeline-run                       # run all layers
/pipeline-run --layer backend       # backend only
/pipeline-run --skip-lint           # skip linting step
```

---

## /queue-run

Process the next item from the feature queue (`scripts/feature-queue.jsonl`).

```
/queue-run [--dry-run] [--issue RF-NNN]
```

**Behaviour:**
1. Read the next unprocessed line from `feature-queue.jsonl`.
2. Create a feature branch (`feature/RF-NNN-description`).
3. Implement the feature following project standards.
4. Run `/pipeline-run` to validate.
5. Mark the queue entry as complete.

**Flags:**
- `--dry-run`: show what would be done without making changes.
- `--issue RF-NNN`: jump to a specific issue instead of the next in queue.

---

## /verify

Run a quick verification pass on the current working tree.

```
/verify [--fix]
```

**Checks:**
1. All files pass lint.
2. All tests pass.
3. No unresolved TODO markers in staged files.
4. Coverage meets thresholds.

**Flags:**
- `--fix`: auto-fix lint issues where possible (ruff format, ruff check --fix).

---

## /feature-branch

Create a new feature branch from the current main branch.

```
/feature-branch RF-NNN short-description
```

**Behaviour:**
1. Fetch latest main.
2. Create branch `feature/RF-NNN-short-description`.
3. Switch to the new branch.

**Example:**
```
/feature-branch OR-12 websocket-auth
# creates: feature/RF-12-websocket-auth
```

---

## /create-pr

Create a pull request for the current feature branch.

```
/create-pr [--draft] [--reviewers user1,user2]
```

**Behaviour:**
1. Push the current branch to origin.
2. Create a PR against `main` with an auto-generated title and body.
3. Body includes: summary of changes, test results, coverage report.

**Flags:**
- `--draft`: create as a draft PR.
- `--reviewers`: request review from specified GitHub users.

---

## Typical Workflow

```bash
/feature-branch OR-15 health-endpoint
# ... implement the feature ...
/verify --fix
/pipeline-run --layer backend
/create-pr
```
