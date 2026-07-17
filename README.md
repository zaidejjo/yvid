<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="yvid/assets/light_logo.png">
    <img src="https://github.com/zaidejjo/yvid/blob/main/assets/logo.png" width="140" alt="YVid">
  </picture>
</p>

<h1 align="center">YVid</h1>

<p align="center">
  <strong>Modern Terminal Video Downloader</strong><br>
  <sub>Interactive · Fast · Cross-Platform</sub>
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/python-≥3.10-007AFF?style=flat&logo=python" alt="Python"></a>
  <a href="https://aur.archlinux.org/packages/yvid"><img src="https://img.shields.io/badge/AUR-yvid-1793D1?style=flat&logo=archlinux" alt="AUR"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat" alt="MIT"></a>
  <a href="https://github.com/zaidejjo/yvid"><img src="https://img.shields.io/badge/github-zaidejjo/yvid-181717?style=flat&logo=github" alt="GitHub"></a>
</p>

---

YVid is a premium terminal video downloader built for speed and power-users. Wrapping `yt-dlp` with an interactive TUI, it turns noisy one-liners into a fluid, guided experience.

<!--
### Key Features

| | Feature | Description |
|---|---|---|
| 🔍 | **Interactive Search** | Type a query instead of a URL — picks from top-5 results |
| 📋 | **Smart Playlists** | Detects `list=` URLs, downloads sequentially with error tolerance |
| 🎵 | **Audio Extraction** | Downloads as MP3 via FFmpeg with configurable quality |
| 🔔 | **Desktop Notifications** | `notify-send` (Linux), `osascript` (macOS), PowerShell Toast (Windows) |
| 🔄 | **Auto-Resume** | Scans `.part` files on startup — picks up where you left off |
| ✂️ | **Zero-Re-Encoding Trim** | FFmpeg stream-copy for instant, lossless cutting |
| 📦 | **Download Archive** | Never download the same video twice — automatic skip |
| ⚙️ | **Persistent Config** | `~/.config/yvid/config.toml` — remembers your defaults |
-->
### Quick Demo

```
$ yvid
  YVid │ Video Downloader  v1.0.0
  ──────────────────────────────────────────

  ❯ 󰗀  Paste video URL or search:
  > never gonna give you up

  ❯ 󰄭  Select a result:
  ▸ Rick Astley — Never Gonna Give You Up [3:32]
    ...

  ❯ 󰐥  Select format:
  ▸ 󰈺  Video (MP4)

  ❯ 󰈺  Select quality:
  ▸ 1080p (Full HD)

  ❯ 󰉋  Output folder:
  > ~/Videos/YVid

  ──────────────────────────────────────────
  󰐥  video    ████████████████████░░  82%  12.3 MB  4.2 MB/s  0:02
  󰗡  Download complete — Rick Astley — Never Gonna Give You Up (3.2 MB)
```

### Install

#### Arch Linux (AUR)

```bash
yay -S yvid
# or
paru -S yvid
```

#### pipx (Linux / macOS / Windows)

```bash
pipx install yvid
```

#### pip (any platform)

```bash
pip install yvid
```

#### One-liner (Linux / macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/zaidejjo/yvid/main/install.sh | bash
```

### Usage

```
yvid                              # Interactive guided flow
yvid --url <URL>                  # Hybrid — prompts for missing options
yvid --url <URL> --format mp4     # Direct download, interactive quality
yvid --url <URL> --format mp3     # Download audio as MP3
yvid --url <URL> --format mp4 --quality 1080p --output ~/Videos
yvid --url "search query"         # Interactive YouTube search
```

**CLI Flags:**

| Flag | Values | Description |
|---|---|---|
| `--url` | URL or search text | Video URL or search query |
| `--format` | `mp4`, `mp3` | Output format |
| `--quality` | `best`, `2160p`, `1080p`, `720p`, `480p` | Video resolution |
| `--trim-start` | `HH:MM:SS` | Trim start time |
| `--trim-end` | `HH:MM:SS` | Trim end time |
| `--subs` | flag | Embed subtitles when available |
| `--output` | path | Output directory |

### GUI Option

YVid also ships a **CustomTkinter desktop GUI** (`yvid-gui`) for users who prefer a visual interface with file browser, progress bars, and one-click downloads.

```bash
yvid-gui
```

### Cross-Platform

| Platform | Status | Notes |
|---|---|---|
| Linux (Arch, Debian, Fedora) | ✅ | Native `notify-send` support |
| macOS | ✅ | Native `osascript` notification banners |
| Windows | ✅ | PowerShell Toast notifications, ANSI via `colorama` |
| Nerd Fonts | ✅ | Auto-detected; falls back to universal Unicode |

### License

MIT — see [LICENSE](LICENSE).
