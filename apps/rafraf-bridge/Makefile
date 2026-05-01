.PHONY: build test lint pkg clean

build:
	go build -o bridge ./cmd/bridge

test:
	go test ./...

lint:
	golangci-lint run

pkg:
	@echo "TODO: pkg target — implemented in T0.5.12"

clean:
	rm -f bridge
