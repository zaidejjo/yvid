#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
#  YVid — One-Click Installer
#  Usage: curl -fsSL https://raw.githubusercontent.com/zaidejjo/yvid/main/install.sh | bash
# ═══════════════════════════════════════════════════════════════

YVID_REPO="https://github.com/zaidejjo/yvid"
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

# ── header ───────────────────────────────────────────────────

cat <<EOF

  ${BOLD}YVid${RESET} ${DIM}— Modern Terminal Video Downloader${RESET}
  ${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}

EOF

# ── detect OS ────────────────────────────────────────────────

OS="unknown"
case "$(uname -s)" in
  Linux)  OS="linux" ;;
  Darwin) OS="macos" ;;
  CYGWIN*|MINGW*|MSYS*) OS="windows" ;;
esac
info "Platform: ${OS}"

# ── Python 3 ─────────────────────────────────────────────────

PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  fail "Python 3 is required but not found."
  dim "Install it from https://www.python.org/downloads/"
fi

ver=$("$PYTHON" --version 2>&1 | grep -oP '\d+\.\d+')
if [ "$(echo "$ver" | cut -d. -f1)" -lt 3 ] || { [ "$(echo "$ver" | cut -d. -f1)" -eq 3 ] && [ "$(echo "$ver" | cut -d. -f2)" -lt 10 ]; }; then
  fail "Python ≥3.10 required (found $ver)."
fi
ok "Python $ver found"

# ── pip / pipx ───────────────────────────────────────────────

INSTALLER=""
if command -v pipx &>/dev/null; then
  INSTALLER="pipx"
elif "$PYTHON" -m pip --version &>/dev/null; then
  INSTALLER="pip"
fi

if [ -z "$INSTALLER" ]; then
  warn "pip not found — installing..."
  "$PYTHON" -m ensurepip --upgrade 2>/dev/null || true
  if "$PYTHON" -m pip --version &>/dev/null; then
    INSTALLER="pip"
  else
    fail "Could not bootstrap pip. Install manually: ${YVID_REPO}"
  fi
fi
ok "Using ${INSTALLER}"

# ── ffmpeg ───────────────────────────────────────────────────

if ! command -v ffmpeg &>/dev/null; then
  warn "ffmpeg not found (required for trimming & audio extraction)"
  case "$OS" in
    linux)
      dim "  Install: sudo apt install ffmpeg       (Debian/Ubuntu)"
      dim "  Install: sudo pacman -S ffmpeg           (Arch)"
      dim "  Install: sudo dnf install ffmpeg         (Fedora)"
      ;;
    macos)
      dim "  Install: brew install ffmpeg"
      ;;
    windows)
      dim "  Download: https://ffmpeg.org/download.html"
      ;;
  esac
else
  ok "ffmpeg found"
fi

# ── install ──────────────────────────────────────────────────

info ""
info "Installing YVid…"

if [ "$INSTALLER" = "pipx" ]; then
  pipx install yvid
else
  "$PYTHON" -m pip install --upgrade yvid
fi

# ── verify ───────────────────────────────────────────────────

if command -v yvid &>/dev/null; then
  ok "YVid installed successfully!"
  dim ""
  dim "  Run ${BOLD}yvid${RESET}${DIM} to start${RESET}"
  dim "  Run ${BOLD}yvid --help${RESET}${DIM} for options${RESET}"
  dim ""
else
  warn "Installation may have completed but 'yvid' wasn't found in PATH."
  dim "  Try: ${BOLD}python3 -m yvid${RESET}"
fi
