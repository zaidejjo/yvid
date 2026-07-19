#!/usr/bin/env bash
# yvid — One-click installer
# Downloads the latest Go binary from GitHub Releases.
# Usage: curl -fsSL https://raw.githubusercontent.com/zaidejjo/yvid/main/install.sh | bash
set -euo pipefail

YVID_REPO="zaidejjo/yvid"
BOLD="\033[1m"
DIM="\033[2m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
CYAN="\033[36m"
RESET="\033[0m"

info()  { printf "${BOLD}%s${RESET}\n" "$*"; }
ok()    { printf "  ${GREEN}✓${RESET}  %s\n" "$*"; }
warn()  { printf "  ${YELLOW}⚠${RESET}  %s\n" "$*"; }
fail()  { printf "  ${RED}✘${RESET}  %s\n" "$*"; exit 1; }
dim()   { printf "  ${DIM}%s${RESET}\n" "$*"; }

# ── header ────────────────────────────────────────────────────
cat <<EOF

  ${BOLD}YVid${RESET} ${DIM}— Modern Video Downloader${RESET}
  ${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}

EOF

# ── detect OS + arch ──────────────────────────────────────────
OS=""
case "$(uname -s)" in
  Linux)  OS="linux" ;;
  Darwin) OS="darwin" ;;
  CYGWIN*|MINGW*|MSYS*) OS="windows" ;;
esac
[ -z "$OS" ] && fail "Unsupported OS: $(uname -s)"

ARCH=""
case "$(uname -m)" in
  x86_64|amd64)  ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
esac
[ -z "$ARCH" ] && fail "Unsupported architecture: $(uname -m)"

info "Platform: ${OS}/${ARCH}"

# ── ffmpeg check ──────────────────────────────────────────────
if ! command -v ffmpeg &>/dev/null; then
  warn "ffmpeg not found (required for trimming & audio extraction)"
  case "$OS" in
    linux)
      dim "  Install: sudo apt install ffmpeg       (Debian/Ubuntu)"
      dim "  Install: sudo pacman -S ffmpeg           (Arch)"
      dim "  Install: sudo dnf install ffmpeg         (Fedora)"
      ;;
    darwin)
      dim "  Install: brew install ffmpeg"
      ;;
    windows)
      dim "  Download: https://ffmpeg.org/download.html"
      ;;
  esac
fi

# ── fetch latest release ──────────────────────────────────────
info ""
info "Fetching latest release..."

GH_API="https://api.github.com/repos/${YVID_REPO}/releases/latest"
RELEASE_JSON="$(curl -fsSL "$GH_API" 2>/dev/null)" || fail "Cannot reach GitHub API. Check internet."

TAG="$(echo "$RELEASE_JSON" | grep '"tag_name"' | cut -d'"' -f4)"
[ -z "$TAG" ] && fail "No releases found for ${YVID_REPO}"

VERSION="${TAG#v}"
ok "Found version ${VERSION}"

# ── find asset URL ────────────────────────────────────────────
# Goreleaser names: yvid_<version>_<os>_<arch>.tar.gz
ASSET_PREFIX="yvid_${VERSION}_${OS}_${ARCH}"
EXTRACT="tar xzf"

if [ "$OS" = "windows" ]; then
  ASSET_PREFIX="yvid_${VERSION}_${OS}_${ARCH}"
  EXTRACT="unzip"
fi

# Find the asset URL from release JSON
ASSET_URL="$(echo "$RELEASE_JSON" | grep -o "\"browser_download_url\":\"[^\"]*${ASSET_PREFIX}[^\"]*\"" | head -1 | cut -d'"' -f4)"
[ -z "$ASSET_URL" ] && fail "No binary found for ${OS}/${ARCH} in release ${TAG}"

# ── install ───────────────────────────────────────────────────
DEST_DIR="${DEST_DIR:-/usr/local/bin}"

# Fallback to ~/.local/bin if /usr/local/bin not writable
if [ ! -w "$DEST_DIR" ]; then
  DEST_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
  mkdir -p "$DEST_DIR"
fi

info ""
info "Downloading ${ASSET_URL##*/}..."
TMP_DIR="$(mktemp -d)"
cd "$TMP_DIR"

curl -fsSL "$ASSET_URL" -o "archive" || fail "Download failed"

# Extract
case "$EXTRACT" in
  "tar xzf")
    tar xzf "archive" 2>/dev/null || fail "Extraction failed"
    ;;
  "unzip")
    unzip -q "archive" 2>/dev/null || fail "Extraction failed"
    ;;
esac

# Find the binary
BINARY="$(find . -type f -name 'yvid' -o -name 'yvid.exe' 2>/dev/null | head -1)"
[ -z "$BINARY" ] && fail "Binary not found in archive"

chmod +x "$BINARY"
cp "$BINARY" "$DEST_DIR/yvid" || fail "Cannot install to ${DEST_DIR}"

cd /
rm -rf "$TMP_DIR"

# ── verify ────────────────────────────────────────────────────
if command -v yvid &>/dev/null; then
  INSTALLED_VER="$(yvid --version 2>&1 | head -1)"
  ok "YVid ${VERSION} installed to ${DEST_DIR}/yvid"
  dim ""
  dim "  Run ${BOLD}yvid${RESET}${DIM} to start${RESET}"
  dim "  Run ${BOLD}yvid --help${RESET}${DIM} for options${RESET}"
  dim "  Run ${BOLD}yvid upgrade${RESET}${DIM} to update later${RESET}"
  dim ""
else
  warn "Binary installed but not in PATH."
  dim "  Add ${DEST_DIR} to your PATH or run:"
  dim "  export PATH=\"\$PATH:${DEST_DIR}\""
  dim ""
fi
