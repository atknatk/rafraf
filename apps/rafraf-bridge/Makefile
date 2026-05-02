.PHONY: build build-bridge build-hook test lint pkg clean

# `build` produces both the bridge daemon AND the V1.2 PreToolUse
# permission hook binary. Both must ship together — the runner
# resolves the hook via os.Executable() sibling lookup so the binaries
# MUST be co-located on the install layout (/usr/local/bin/ or the
# Makefile-relative dev layout used here).
build: build-bridge build-hook

build-bridge:
	go build -o rafraf-bridge ./cmd/bridge

build-hook:
	go build -o rafraf-perm-hook ./internal/cmd/rafraf-perm-hook

test:
	go test -race -count=1 ./...

lint:
	golangci-lint run

pkg:
	@echo "TODO: pkg target — implemented in T0.5.12 (must include rafraf-perm-hook)"

clean:
	rm -f rafraf-bridge rafraf-perm-hook
