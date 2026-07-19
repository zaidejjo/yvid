# yvid — Makefile
#
# Targets:
#   build         Build for host platform
#   build-all     Cross-compile for all platforms
#   install       Build and install to $GOPATH/bin
#   clean         Remove build artifacts
#   lint          Run golangci-lint
#   test          Run unit tests
#   tidy          Tidy go modules

BINARY   := yvid
VERSION  := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
COMMIT   := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
DATE     := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)

# Go build flags
LDFLAGS  := -ldflags="-X 'github.com/zaidejjo/yvid/internal/cli.version=$(VERSION)' \
					 -X 'github.com/zaidejjo/yvid/internal/cli.commit=$(COMMIT)' \
					 -X 'github.com/zaidejjo/yvid/internal/cli.date=$(DATE)' \
					 -s -w"

# Output directory
OUTDIR   := build

# Target platforms for cross-compilation
PLATFORMS := linux/amd64 linux/arm64 darwin/amd64 darwin/arm64 windows/amd64

.PHONY: all build build-all install clean lint test tidy

all: build

# ── Host build ────────────────────────────────────────────────

build:
	@echo "  Building $(BINARY) $(VERSION) for $(shell go env GOOS)/$(shell go env GOARCH)..."
	go build $(LDFLAGS) -o $(OUTDIR)/$(BINARY) ./cmd/yvid
	@echo "  ✓  $(OUTDIR)/$(BINARY)"

# ── Cross-compilation ─────────────────────────────────────────

build-all:
	@echo "  Cross-compiling $(BINARY) $(VERSION)..."
	@mkdir -p $(OUTDIR)
	@for platform in $(PLATFORMS); do \
		os=$$(echo $$platform | cut -d/ -f1); \
		arch=$$(echo $$platform | cut -d/ -f2); \
		suffix=""; \
		[ "$$os" = "windows" ] && suffix=".exe"; \
		output="$(OUTDIR)/$(BINARY)_$${os}_$${arch}$${suffix}"; \
		echo "    $$platform → $$output"; \
		GOOS=$$os GOARCH=$$arch CGO_ENABLED=0 go build $(LDFLAGS) -o "$$output" ./cmd/yvid; \
	done
	@echo "  ✓  All builds complete"
	@ls -lh $(OUTDIR)/

# ── Install ───────────────────────────────────────────────────

install: build
	@cp $(OUTDIR)/$(BINARY) $(GOPATH)/bin/$(BINARY)
	@echo "  ✓  Installed to $(GOPATH)/bin/$(BINARY)"

# ── Clean ─────────────────────────────────────────────────────

clean:
	@rm -rf $(OUTDIR)
	@echo "  ✓  Cleaned"

# ── Lint ──────────────────────────────────────────────────────

lint:
	@golangci-lint run ./...

# ── Test ──────────────────────────────────────────────────────

test:
	@go test ./... -v -count=1

# ── Tidy ──────────────────────────────────────────────────────

tidy:
	@go mod tidy
	@echo "  ✓  Modules tidied"

# ── Release archive ───────────────────────────────────────────

release: build-all
	@echo "  Creating release archives..."
	@for f in $(OUTDIR)/$(BINARY)_*; do \
		if [ -f "$$f" ]; then \
			base=$$(basename "$$f"); \
			ext=""; \
			case "$$base" in *.exe) ext=".exe"; base=$${base%.exe};; esac; \
			tar_name="$$base.tar.gz"; \
			tar czf "$(OUTDIR)/$$tar_name" -C $(OUTDIR) "$$base$$ext"; \
			rm "$$f"; \
		fi; \
	done
	@echo "  ✓  Archives created"
	@ls -lh $(OUTDIR)/
