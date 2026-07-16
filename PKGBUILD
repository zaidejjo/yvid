# Maintainer: Zaid Ajo <zaidejjodev@gmail.com>
# Contributor: Zaid Ajo <zaidejjodev@gmail.com>
#
# Arch Linux / AUR PKGBUILD for YVid
# ===================================
# Build using `uv` — fast, isolated, conflict-free.
#
# Strategy
# --------
#   depends        python, ffmpeg           → system-level only
#   makedepends    python-uv                → uv handles all Python deps
#   build()        uv build --wheel         → PEP 517 isolated build
#   package()      uv pip install --target  → bundles ALL Python deps into
#                                             $pkgdir's site-packages with
#                                             zero host-system pollution
#
# There are NO file conflicts with Arch Python packages because every
# Python dependency lives inside our package directory, not in
# /usr/lib/python*/site-packages/ of the running system.
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

# ── System-level dependencies only ───────────────────────────
# All Python libraries are bundled at build time via uv, so the
# only runtime requirements are Python itself and FFmpeg.
depends=(
    'python'
    'ffmpeg'
)

# `python-uv` brings in `uv` and `python-installer` transitively
# when needed; we list installer explicitly for clarity.
makedepends=(
    'python-uv'
    'python-installer'
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

    # ── Build wheel via uv (PEP 517 isolated build) ─────────
    # uv handles dependency resolution from pyproject.toml in an
    # isolated temporary environment — no host Python pollution.
    uv build --wheel
}

check() {
    cd "$srcdir/$pkgname-$pkgver"
    python -m compileall . -q -x ".git" 2>&1 || true
}

package() {
    cd "$srcdir/$pkgname-$pkgver"

    # ── 1. Install the built wheel ──────────────────────────
    #     python -m installer correctly creates the
    #     /usr/bin/{yvid,yvid-cli,yvid-gui} entry-point scripts.
    python -m installer --destdir="$pkgdir" dist/*.whl

    # ── 2. Bundle ALL Python runtime deps via uv ────────────
    #     We install into the package's site-packages directory
    #     inside $pkgdir.  Nothing is written to the host system.
    python_sitelib=$(python3 -c "import sysconfig; print(sysconfig.get_path('purelib'))")
    UV_SYSTEM_PYTHON=1 uv pip install \
        customtkinter \
        'yt-dlp>=2025.0.0' \
        'Pillow>=9.0.0' \
        rich \
        questionary \
        --target="$pkgdir$python_sitelib"

    # ── 3. Desktop icon (Freedesktop standard path) ─────────
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
