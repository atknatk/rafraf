.PHONY: all backend ios agent lint test clean verify

all: backend agent

# ─── Backend ──────────────────────────────────────────
backend:
	cd apps/backend && pip install -e ".[dev]"

# ─── iOS ──────────────────────────────────────────────
ios:
	@echo "TODO: xcodebuild -workspace apps/ios/RafRaf.xcworkspace -scheme RafRaf build"

# ─── Agent ────────────────────────────────────────────
agent:
	cd apps/agent && pip install -e ".[dev]"

# ─── Lint ─────────────────────────────────────────────
lint:
	cd apps/backend && ruff check . && mypy .
	cd apps/agent && ruff check . && mypy .

# ─── Test ─────────────────────────────────────────────
test:
	cd apps/backend && pytest --cov=app --cov-report=term-missing
	cd apps/agent && pytest --cov=agent --cov-report=term-missing

# ─── Clean ────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name dist -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name build -not -path "./.build" -exec rm -rf {} + 2>/dev/null || true

# ─── Verify (full CI pipeline locally) ────────────────
verify: lint test
	@echo "All checks passed."
