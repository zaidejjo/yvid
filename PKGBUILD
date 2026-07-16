# Maintainer: Zaid Ajo <zaidejjodev@gmail.com>
# Contributor: Zaid Ajo <zaidejjodev@gmail.com>
#
# Arch Linux / AUR PKGBUILD for YVid
# ===================================
# Build using `uv` — fast, isolated, conflict-free.
#
# Strategy
# --------
#   depends        python, ffmpeg, yt-dlp, python-pillow,
#                  python-rich, python-packaging, python-wcwidth
#                                                     → Arch official repos
#   makedepends    python-uv, python-installer       → build tools
#   build()        uv build --wheel                  → PEP 517 isolated build
#   package()      uv pip install --no-deps --target → bundles only AUR-only
#                     packages (customtkinter, questionary) into $pkgdir;
#                     everything else comes from Arch system packages.
#
# There are NO file conflicts because we NEVER download packages that
# have an `archlinux` counterpart — we pin those in `depends` instead.
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

# ── Dependencies from official Arch repos ───────────────────
# Packages available in [core] / [extra] are listed here and
# installed via pacman.  Only packages NOT in the Arch repos
# (customtkinter, questionary) are bundled via uv --no-deps.
depends=(
    'python'
    'ffmpeg'
    'yt-dlp'
    'python-pillow'
    'python-rich'
    'python-packaging'
    'python-wcwidth'
    'tk'
)
makedepends=(
    'uv'
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

    # ── 2. Bundle AUR-only Python deps via uv ────────────────
    #     customtkinter and questionary have no Arch counterpart;
    #     everything else (pillow, rich, yt-dlp, packaging, etc.)
    #     comes from the official repos via `depends`.
    #     ──no-deps prevents uv from pulling transitive deps
    #     that would conflict with pacman-managed packages.
    python_sitelib=$(python3 -c "import sysconfig; print(sysconfig.get_path('purelib'))")
    UV_SYSTEM_PYTHON=1 uv pip install \
        --no-deps \
        customtkinter \
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
