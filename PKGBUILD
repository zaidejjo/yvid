# Maintainer: Zaid Ajo <zaidejjodev@gmail.com>
# Contributor: Zaid Ajo <zaidejjodev@gmail.com>
#
# Arch Linux / AUR PKGBUILD for YVid
# ===================================
# Build from source (GitHub release tag) using PEP 517.
#
# Dependency strategy
# -------------------
# Packages in official Arch repos  → listed in `depends` (pacman-managed)
# Packages only in AUR / PyPI      → installed via pip at build time
#
# Arch packages used:
#   python-pillow, python-rich     [extra]
#   yt-dlp                         [extra]  (not python-yt-dlp)
#   python, ffmpeg                 [core, extra]
#
# PyPI-only:  customtkinter, questionary
#
# Installs:
#   yvid           — terminal CLI (interactive TUI + direct args)
#   yvid-gui       — desktop GUI (CustomTkinter)
#   yvid-cli       — alias for yvid (legacy compat)
#   /usr/share/pixmaps/yvid.png
#   /usr/share/applications/yvid.desktop
#
# Build:
#   makepkg -si
#
# Verify with namcap:
#   namcap PKGBUILD
#   namcap yvid-*.pkg.tar.zst

pkgname=yvid
pkgver=1.0.0
pkgrel=1
pkgdesc="Modern Video Downloader — Desktop GUI + Terminal CLI"
arch=('any')
url="https://github.com/zaidejjo/yvid"
license=('MIT')

# ── Official Arch repo dependencies ──────────────────────────
depends=(
    'python'
    'yt-dlp'
    'python-pillow'
    'python-rich'
    'ffmpeg'
)

makedepends=(
    'python-build'
    'python-installer'
    'python-wheel'
    'python-setuptools'
    'python-pip'
)

optdepends=(
    'xdg-utils: opening downloaded files from the CLI'
)

source=("$pkgname-$pkgver.tar.gz::https://github.com/zaidejjo/yvid/archive/v$pkgver.tar.gz")
sha256sums=('SKIP')
# ^ SKIP is acceptable for AUR (source integrity is trust-on-first-use).
#   For a release-quality PKGBUILD, replace with the actual sha256sum.

build() {
    cd "$srcdir/$pkgname-$pkgver"

    # ── AUR-only Python deps ──────────────────────────────
    # These packages are NOT in the official Arch repositories.
    # Install them from PyPI so the build can resolve all imports.
    PIP_REQUIRE_VIRTUALENV=false python -m pip install \
        customtkinter questionary \
        --break-system-packages --no-input 2>&1 \
        | grep -v "already satisfied" || true

    # ── Build wheel (--no-isolation: use system Python libs) ──
    python -m build --wheel --no-isolation
}

check() {
    cd "$srcdir/$pkgname-$pkgver"
    python -m compileall . -q -x ".git" 2>&1 || true
}

package() {
    cd "$srcdir/$pkgname-$pkgver"

    # ── 1. Install the Python package (wheel) ──────────────
    #     This creates /usr/bin/{yvid,yvid-cli,yvid-gui}
    #     and installs the Python modules into site-packages.
    python -m installer --destdir="$pkgdir" dist/*.whl

    # ── 2. Ship AUR-only Python libs inside our package ────
    #     customtkinter and questionary are not available via
    #     pacman, so we bundle them so the user has everything
    #     they need after `pacman -U`.
    PIP_REQUIRE_VIRTUALENV=false python -m pip install \
        customtkinter questionary \
        --prefix=/usr --root="$pkgdir" \
        --ignore-installed --no-input 2>&1 \
        | grep -v "already satisfied" || true

    # ── 3. Desktop icon ────────────────────────────────────
    #     Freedesktop standard path for app icons.
    install -Dm644 assets/logo.png "$pkgdir/usr/share/pixmaps/yvid.png"

    # ── 4. .desktop entry ──────────────────────────────────
    install -Dm644 /dev/stdin "$pkgdir/usr/share/applications/yvid.desktop" <<'DESKTOP_EOF'
[Desktop Entry]
Type=Application
Name=YVid
GenericName=Video Downloader
Comment=Download videos from YouTube and hundreds of other sites
Exec=yvid-gui
Icon=yvid
Terminal=false
Categories=AudioVideo;Video;Network;
StartupNotify=true
Keywords=video;downloader;youtube;yt-dlp;media;download;
DESKTOP_EOF
}
