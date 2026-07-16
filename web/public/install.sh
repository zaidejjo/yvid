#!/usr/bin/env bash
#
# YVid — Smart Installer Script
# ==============================
# Auto-detect OS/arch, download the latest YVid release, and install it.
#
# Usage: curl -fsSL https://yvid.pages.dev/install.sh | sh
#
# Supported platforms:
#   - macOS  (x86_64, arm64)
#   - Linux  (x86_64, aarch64)
#   - Windows (x86_64) — via Git BASH / WSL
#
# Environment variables:
#   YVID_VERSION  — pin a specific version (e.g., "v2.0.0")
#   YVID_INSTALL  — custom install path (default: /usr/local/bin)
#   YVID_DRY_RUN  — if set, print actions without executing
# ==============================================================================

set -euo pipefail

# ─── Colors ────────────────────────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"
CYAN="\033[36m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"

info()  { printf "${CYAN}%s${RESET}\n" "$*"; }
ok()    { printf "${GREEN}✔ %s${RESET}\n" "$*"; }
warn()  { printf "${YELLOW}⚠ %s${RESET}\n" "$*"; }
error() { printf "${RED}✖ %s${RESET}\n" "$*"; exit 1; }

# ─── Detect OS and Architecture ────────────────────────────────────────────
detect_os() {
  case "$(uname -s)" in
    Darwin*)  echo "darwin"  ;;
    Linux*)   echo "linux"   ;;
    CYGWIN*|MINGW*|MSYS*) echo "windows" ;;
    *)        error "Unsupported OS: $(uname -s). Visit https://yvid.pages.dev/install for manual installation." ;;
  esac
}

detect_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo "x86_64"  ;;
    aarch64|arm64) echo "aarch64" ;;
    *)  warn "Unknown architecture: $(uname -m). Falling back to x86_64."; echo "x86_64" ;;
  esac
}

# ─── Determine latest version from GitHub ──────────────────────────────────
fetch_latest_version() {
  if [ -n "${YVID_VERSION:-}" ]; then
    echo "$YVID_VERSION"
    return
  fi

  info "✦ Fetching latest release..."
  local url="https://api.github.com/repos/zaidejjo/yvid/releases/latest"

  if command -v curl &>/dev/null; then
    version=$(curl -fsSL "$url" 2>/dev/null | grep '"tag_name"' | sed 's/.*"tag_name": "//;s/".*//' || true)
  elif command -v wget &>/dev/null; then
    version=$(wget -qO- "$url" 2>/dev/null | grep '"tag_name"' | sed 's/.*"tag_name": "//;s/".*//' || true)
  fi

  if [ -z "$version" ]; then
    warn "Could not fetch latest version from GitHub. Using v2.0.0 as fallback."
    echo "v2.0.0"
  else
    echo "$version"
  fi
}

# ─── Main Install Routine ──────────────────────────────────────────────────
main() {
  printf "\n${BOLD}  ╭─────────────────────────────────╮${RESET}\n"
  printf "${BOLD}  │ ${CYAN}  YVid — Smart Installer ${RESET}${BOLD}        │${RESET}\n"
  printf "${BOLD}  ╰─────────────────────────────────╯${RESET}\n\n"

  local os=$(detect_os)
  local arch=$(detect_arch)
  local version=$(fetch_latest_version)

  info "✦ Detected: ${os} (${arch})"
  info "✦ Version:  ${version}"

  # Build download URL (example pattern — adjust to match your release assets)
  # Expected: yvid-<version>-<os>-<arch>.tar.gz
  local filename="yvid-${version}-${os}-${arch}.tar.gz"
  local download_url="https://github.com/zaidejjo/yvid/releases/download/${version}/${filename}"

  # Install path
  local install_dir="${YVID_INSTALL:-/usr/local/bin}"

  if [ -n "${YVID_DRY_RUN:-}" ]; then
    info "✦ [DRY-RUN] Would download: ${download_url}"
    info "✦ [DRY-RUN] Would install to: ${install_dir}/yvid"
    ok "Dry-run complete."
    exit 0
  fi

  # Create temp directory
  local tmpdir
  tmpdir=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$tmpdir'" EXIT

  # Download
  info "✦ Downloading ${filename}..."
  if command -v curl &>/dev/null; then
    curl -fsSL "$download_url" -o "$tmpdir/$filename"
  elif command -v wget &>/dev/null; then
    wget -qO "$tmpdir/$filename" "$download_url"
  else
    error "Neither curl nor wget found. Install one of them and retry."
  fi

  # Extract
  info "✦ Extracting..."
  tar xzf "$tmpdir/$filename" -C "$tmpdir"

  # Find binary
  local binary
  binary=$(find "$tmpdir" -name "yvid" -type f 2>/dev/null | head -1)
  if [ -z "$binary" ]; then
    error "Binary not found in archive. The release format may have changed."
  fi

  # Install
  info "✦ Installing to ${install_dir}/yvid..."
  mkdir -p "$install_dir"

  if [ -f "${install_dir}/yvid" ]; then
    warn "Overwriting existing installation at ${install_dir}/yvid"
  fi

  install -m 755 "$binary" "${install_dir}/yvid"

  # Verify
  if command -v yvid &>/dev/null; then
    ok "YVid ${version} installed successfully!"
    printf "\n  Run ${CYAN}yvid --help${RESET} to get started, or ${CYAN}yvid --gui${RESET} to launch the GUI.\n"
  else
    warn "Installation complete, but ${install_dir}/yvid is not in your PATH."
    warn "Add it: export PATH=\"\$PATH:${install_dir}\""
  fi
}

main
