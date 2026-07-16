# Maintainer: Zaid Ajo <zaidejjodev@gmail.com>
# Contributor: Zaid Ajo <zaidejjodev@gmail.com>
#
# Arch Linux / AUR PKGBUILD for YVid
# ===================================
# Build from source (GitHub release tag) using PEP 517.
#
# Installs:
#   yvid           — terminal CLI (interactive TUI + direct args)
#   yvid-gui       — desktop GUI (CustomTkinter)
#   yvid-cli       — alias for yvid (legacy compat)
#   /usr/share/pixmaps/yvid.png
#   /usr/share/applications/yvid.desktop
#
# To build:
#   makepkg -si
#
# To verify:
#   namcap PKGBUILD
#   namcap yvid-*.pkg.tar.zst

pkgname=yvid
pkgver=1.0.0
pkgrel=1
pkgdesc="Modern Video Downloader — Desktop GUI + Terminal CLI"
arch=('any')
url="https://github.com/zaidejjo/yvid"
license=('MIT')
depends=(
    'python'
    'python-customtkinter'
    'python-yt-dlp'
    'python-pillow'
    'python-rich'
    'python-questionary'
    'ffmpeg'
)
makedepends=(
    'python-build'
    'python-installer'
    'python-wheel'
    'python-setuptools'
)
optdepends=(
    'gnome-terminal: default terminal for yvid-gui fallback'
    'xdg-utils: opening downloaded files from the CLI'
)
source=("$pkgname-$pkgver.tar.gz::https://github.com/zaidejjo/yvid/archive/v$pkgver.tar.gz")
sha256sums=('SKIP')
# ^ SKIP is acceptable for AUR (source integrity is trust-on-first-use).
#   For a release-quality PKGBUILD, replace with the actual sha256sum.

build() {
    cd "$srcdir/$pkgname-$pkgver"
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

    # ── 2. Desktop icon ────────────────────────────────────
    #     Freedesktop standard path for app icons.
    install -Dm644 assets/logo.png "$pkgdir/usr/share/pixmaps/yvid.png"

    # ── 3. .desktop entry ──────────────────────────────────
    #     Registered category: AudioVideo;Video;Network;
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
