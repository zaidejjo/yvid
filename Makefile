# yvid — Makefile
#
# Targets:
#   build         Build for host platform
#   build-all     Cross-compile for all platforms
#   release       Create release archives (goreleaser-compatible naming)
#   install       Build and install to $GOPATH/bin
#   clean         Remove build artifacts
#   lint          Run golangci-lint
#   test          Run unit tests
#   tidy          Tidy go modules

BINARY   := yvid
VERSION  := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
COMMIT   := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
DATE     := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)

# Go build flags — inject version info via LDFLAGS
LDFLAGS  := -ldflags="-X 'github.com/zaidejjo/yvid/internal/cli.version=$(VERSION)' \
					 -X 'github.com/zaidejjo/yvid/internal/cli.commit=$(COMMIT)' \
					 -X 'github.com/zaidejjo/yvid/internal/cli.date=$(DATE)' \
					 -s -w"

OUTDIR   := build

# Target platforms (matching goreleaser)
PLATFORMS := linux/amd64 linux/arm64 darwin/amd64 darwin/arm64 windows/amd64

.PHONY: all build build-all release install clean lint test tidy

all: build

# ── Host build ────────────────────────────────────────────────

build:
	@echo "  Building $(BINARY) $(VERSION) for $(shell go env GOOS)/$(shell go env GOARCH)..."
	@mkdir -p $(OUTDIR)
	go build $(LDFLAGS) -o $(OUTDIR)/$(BINARY) ./cmd/yvid
	@echo "  ✓  $(OUTDIR)/$(BINARY) ($(shell ls -lh $(OUTDIR)/$(BINARY) | awk '{print $$5}'))"

# ── Cross-compilation ─────────────────────────────────────────

build-all:
	@echo "  Cross-compiling $(BINARY) $(VERSION)..."
	@mkdir -p $(OUTDIR)
	@for platform in $(PLATFORMS); do \
		os=$$(echo $$platform | cut -d/ -f1); \
		arch=$$(echo $$platform | cut -d/ -f2); \
		suffix=""; \
		[ "$$os" = "windows" ] && suffix=".exe"; \
		output="$(OUTDIR)/$(BINARY)-$(VERSION)-$${os}-$${arch}$${suffix}"; \
		echo "    $$platform → $$output"; \
		GOOS=$$os GOARCH=$$arch CGO_ENABLED=0 go build $(LDFLAGS) -o "$$output" ./cmd/yvid; \
	done
	@echo "  ✓  All builds complete"
	@ls -lh $(OUTDIR)/

# ── Release archives (goreleaser-compatible naming) ──────────

release: build-all
	@echo "  Creating release archives..."
	@for f in $(OUTDIR)/$(BINARY)-$(VERSION)-*; do \
		if [ -f "$$f" ]; then \
			base=$$(basename "$$f"); \
			ext=""; \
			case "$$base" in *.exe) ext=".exe"; base=$${base%.exe};; esac; \
			archive_name="$$base.tar.gz"; \
			[ "$$ext" = ".exe" ] && archive_name="$$base.zip"; \
			if [ "$$ext" = ".exe" ]; then \
				(cd $(OUTDIR) && zip "$$archive_name" "$$base$$ext") 2>/dev/null; \
			else \
				tar czf "$(OUTDIR)/$$archive_name" -C $(OUTDIR) "$$base$$ext"; \
			fi; \
			rm "$$f"; \
			echo "    ✓  $$archive_name"; \
		fi; \
	done
	@echo "  ✓  Release archives created"
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
