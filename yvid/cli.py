#!/usr/bin/env python3
"""
YVid-CLI — Modern Terminal Video Downloader

Minimal, interactive, premium UX.
Built with yt-dlp + Rich + Questionary + prompt_toolkit.

Usage:
    yvid                              Interactive guided flow
    yvid --url <URL>                  Hybrid — prompts for missing options
    yvid --url <URL> --format mp4 --quality 1080p   Direct download
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys

import colorama
from pathlib import Path

# ── TOML support (Python ≥3.11 has tomllib built-in) ─────
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

import questionary
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.key_binding import KeyBindings
from questionary import Style as QStyle
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.text import Text

from .core.config import (
    APP_NAME,
    VERSION,
    DEFAULT_OUTPUT_DIR,
    FORMAT_VIDEO_QUALITY,
)
from .core.helpers import (
    format_bytes,
    format_error_message,
    is_valid_url,
    parse_time,
)
from .core.download_thread import DownloadThread


# ═══════════════════════════════════════════════════════════════
#  NERD FONT ICONS  —  with universal-Unicode fallback
# ═══════════════════════════════════════════════════════════════


def _nerd_fonts_available() -> bool:
    """Detect whether the terminal supports Nerd Font PUA codepoints.

    Checks the ``YVID_NO_NERD_FONTS`` environment variable, and on
    Windows requires a modern terminal (Windows Terminal) rather than
    legacy ``cmd.exe`` or PowerShell ISE.
    """
    if os.environ.get("YVID_NO_NERD_FONTS"):
        return False
    if sys.platform == "win32" and "WT_SESSION" not in os.environ:
        return False
    return True


_USE_NERD = _nerd_fonts_available()

if _USE_NERD:
    # Nerd Font Private Use Area codepoints
    _NF = "󰈺"  # video    (nf-fa-film)
    _NF_A = "󰎆"  # audio    (nf-fa-music)
    _NF_L = "󰗀"  # link     (nf-md-link_variant)
    _NF_F = "󰉋"  # folder   (nf-fa-folder_open)
    _NF_D = "󰐥"  # download (nf-fa-download)
    _NF_C = "󰗡"  # check    (nf-fa-check_circle)
    _NF_X = "󰅖"  # close    (nf-fa-close)
    _NF_R = "󰑖"  # refresh  (nf-fa-refresh)
    _NF_G = "󰓎"  # gear     (nf-fa-cog)
    _NF_S = "󰌫"  # cut      (nf-md-content_cut)
    _NF_B = "󰇆"  # subs     (nf-fa-cc)
    _NF_PL = "󰫧"  # playlist (nf-md-playlist_music)
    _NF_MS = "󰄭"  # search   (nf-fa-search)
else:
    # Universal Unicode fallback — every modern terminal supports these
    _NF = "\u25b6"  # ▶  (black right-pointing triangle)
    _NF_A = "\u266b"  # ♫  (beamed eighth notes)
    _NF_L = "\U0001f517"  # 🔗 (link)
    _NF_F = "\U0001f4c1"  # 📁 (folder)
    _NF_D = "\u2b07"  # ⬇  (downwards arrow)
    _NF_C = "\u2714"  # ✔  (check mark)
    _NF_X = "\u2718"  # ✘  (heavy ballot X)
    _NF_R = "\u21bb"  # ↻  (clockwise open circle arrow)
    _NF_G = "\u2699"  # ⚙  (gear)
    _NF_S = "\u2702"  # ✂  (black scissors)
    _NF_B = "\U0001f4da"  # 📚 (books — subtitles / captions)
    _NF_PL = "\U0001f4cb"  # 📋 (clipboard — playlist)
    _NF_MS = "\U0001f50d"  # 🔍 (magnifying glass — search)


# ═══════════════════════════════════════════════════════════════
#  QUESTIONARY STYLE  — subtle, premium feel
# ═══════════════════════════════════════════════════════════════

QUESTIONARY_STYLE = QStyle(
    [
        ("qmark", "bold fg:#007AFF"),
        ("question", "bold fg:white"),
        ("answer", "fg:green bold"),
        ("pointer", "bold fg:#007AFF"),
        ("highlighted", "bold fg:#007AFF"),
        ("selected", "fg:green"),
        ("separator", "fg:gray"),
        ("instruction", "fg:gray italic"),
        ("text", ""),
        ("disabled", "fg:gray"),
    ]
)


def _ask(qtype: str, *args, **kwargs):
    """Create a questionary prompt with consistent styling and the ❯ qmark."""
    kwargs.setdefault("qmark", "❯")
    kwargs.setdefault("style", QUESTIONARY_STYLE)
    return getattr(questionary, qtype)(*args, **kwargs)


def _safe_remove(path: str) -> None:
    """Remove a file, silently ignoring errors."""
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
#  MAIN CLI APPLICATION
# ═══════════════════════════════════════════════════════════════


class YVidCLI:
    """The YVid-CLI interactive terminal application."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.console = Console()
        self.config: dict = {}
        self._last_error: str = ""

        # Track download result for _show_completion / _ask_download_another
        self.last_output_path: str = ""

        # ── persistent config (Feature 3) ──────────────────
        self.settings: dict = {}
        self._init_config()

    # ── cross-platform config directory ───────────────────

    @staticmethod
    def _get_config_dir() -> str:
        """Return the platform-appropriate config directory path.

        - **POSIX (Linux / macOS)**: ``~/.config/yvid``
        - **Windows**: ``%APPDATA%\\yvid``
        """
        if sys.platform == "win32":
            return os.path.join(os.environ["APPDATA"], "yvid")
        return str(Path.home() / ".config" / "yvid")

    # ── persistent configuration (Feature 3) ────────────────

    DEFAULT_CONFIG_TOML = """\
[defaults]
output_dir = "~/Videos/YVid"
default_format = "video"
default_quality = "best"
theme_color = "#007AFF"
"""

    def _init_config(self) -> None:
        """Ensure config dir + default file exist, then load settings."""
        config_dir = self._get_config_dir()
        config_path = os.path.join(config_dir, "config.toml")

        if not os.path.isdir(config_dir):
            os.makedirs(config_dir, exist_ok=True)
            with open(config_path, "w") as f:
                f.write(self.DEFAULT_CONFIG_TOML)
            self._dim(f"Created default config: [bold]{config_path}[/bold]")

        self.settings = self._parse_config(config_path)

    def _parse_config(self, path: str) -> dict:
        """Read config.toml and return a flat dict with defaults applied."""
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            data = {}

        raw = data.get("defaults", {})
        return {
            "output_dir": os.path.expanduser(raw.get("output_dir", DEFAULT_OUTPUT_DIR)),
            "default_format": str(raw.get("default_format", "video")),
            "default_quality": str(raw.get("default_quality", "best")),
            "theme_color": str(raw.get("theme_color", "#007AFF")),
        }

    # ── session / resume (Feature 4) ────────────────────────

    def _save_session(self) -> None:
        """Persist current config to session.json for resume."""
        session_dir = self._get_config_dir()
        os.makedirs(session_dir, exist_ok=True)
        session_path = os.path.join(session_dir, "session.json")
        try:
            with open(session_path, "w") as f:
                json.dump(self.config, f, default=str, indent=2)
        except Exception:
            pass

    def _clear_session(self) -> None:
        """Remove session file after a successful download."""
        session_path = os.path.join(self._get_config_dir(), "session.json")
        try:
            if os.path.isfile(session_path):
                os.remove(session_path)
        except Exception:
            pass

    def _check_resume(self) -> bool:
        """Scan output_dir for *.part files; offer to resume on match.

        Returns True when the user chooses to resume and the download
        (with its completion / "download another" flow) runs to
        completion inside this call.  Returns False to continue with
        the normal interactive flow.
        """
        output_dir = self.settings.get("output_dir", DEFAULT_OUTPUT_DIR)
        if not os.path.isdir(output_dir):
            return False

        part_files = [f for f in os.listdir(output_dir) if f.endswith(".part")]
        if not part_files:
            return False

        self.console.print()
        resume = _ask(
            "confirm",
            "Interrupted download detected.  Resume?",
            default=True,
        ).ask()
        if not resume:
            # User declined — clean up stale session
            self._clear_session()
            return False

        # Try loading the saved session
        session_path = os.path.join(self._get_config_dir(), "session.json")
        if not os.path.isfile(session_path):
            self._yellow("No saved session found.  Please start a new download.")
            return False

        try:
            with open(session_path) as f:
                self.config = json.load(f)
        except Exception as exc:
            self._yellow(f"Could not read session: {exc}")
            return False

        self.console.print(f"  {_NF_D}  [dim]Resuming interrupted download\u2026[/dim]")
        self.console.print()

        # Run the download (dispatches single / playlist automatically)
        self._execute_download()
        self._clear_session()
        self._show_completion()

        return True

    # ── public entry point ──────────────────────────────────

    def run(self) -> None:
        """Main loop — check resume, download, optionally repeat."""
        while True:
            try:
                self._show_header()

                # Feature 4: check for interrupted .part downloads
                if self._check_resume():
                    # Resume call handled the full flow — jump to "another?"
                    if not self._ask_download_another():
                        break
                    continue

                self._interactive_flow()
                self._save_session()
                self._execute_download()
                self._clear_session()
            except DownloadError as exc:
                self._clear_session()
                if self._handle_download_error(exc):
                    continue
                sys.exit(1)
            except KeyboardInterrupt:
                self._clear_session()
                self.console.print()
                self._dim("Cancelled.")
                sys.exit(0)
            except Exception as exc:
                self._clear_session()
                self.console.print(f"\n  [red]{_NF_X}  {exc}[/red]")
                sys.exit(1)

            self._show_completion()
            if not self._ask_download_another():
                break

    # ── rich helpers ────────────────────────────────────────

    def _dim(self, msg: str) -> None:
        self.console.print(f"  [dim]{msg}[/dim]")

    def _green(self, msg: str) -> None:
        self.console.print(f"  [green]{msg}[/green]")

    def _yellow(self, msg: str) -> None:
        self.console.print(f"  [yellow]{msg}[/yellow]")

    # ── header ──────────────────────────────────────────────

    def _show_header(self) -> None:
        self.console.clear()
        title = Text.assemble(
            ("YVid", "bold cyan"),
            (" │ ", "dim"),
            ("Video Downloader", "cyan"),
            ("  ", ""),
            (f"v{VERSION}", "dim"),
        )
        self.console.print(title)
        self.console.print("[dim]\u2500" * 42 + "[/dim]")
        self.console.print()

    # ── helpers: search + playlist info ─────────────────────

    @staticmethod
    def _format_duration(seconds: int | None) -> str:
        """Convert seconds to 'M:SS' or 'H:MM:SS' or '--:--' if None."""
        if not seconds:
            return "--:--"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _search_youtube(self, query: str) -> str | None:
        """Search YouTube with ytsearch5, let user pick, return video URL or None."""
        import yt_dlp

        self.console.print(
            f'  {_NF_MS}  [dim]Searching YouTube for "{query}"\u2026[/dim]'
        )

        try:
            with yt_dlp.YoutubeDL(
                {
                    "quiet": True,
                    "no_warnings": True,
                    "extract_flat": True,
                }
            ) as ydl:
                info = ydl.extract_info(f"ytsearch5:{query}", download=False)
                entries = info.get("entries", [])
        except Exception as exc:
            self._yellow(f"Search failed: {exc}")
            return None

        if not entries:
            self._yellow("No results found.")
            return None

        result_map: dict[str, str] = {}
        for entry in entries:
            title = (entry.get("title") or "Unknown").strip()
            dur = self._format_duration(entry.get("duration"))
            uploader = entry.get("uploader") or entry.get("channel") or ""
            url = entry.get("url") or entry.get("webpage_url") or ""

            # Build a clean display label capped at ~72 chars
            label = f"{title}  [{dur}]"
            if uploader:
                label += f"  \u2014  {uploader}"
            if len(label) > 72:
                label = label[:69] + "\u2026"
            result_map[label] = url

        self.console.print()
        chosen = _ask(
            "select",
            f"{_NF_MS}  Select a result:",
            choices=list(result_map.keys()),
        ).ask()

        if chosen is None:
            return None
        return result_map[chosen]

    def _fetch_playlist_info(self, url: str) -> tuple[str, int, list] | None:
        """Return (title, count, entries) for a playlist URL, or None."""
        import yt_dlp

        try:
            with yt_dlp.YoutubeDL(
                {
                    "quiet": True,
                    "no_warnings": True,
                    "extract_flat": True,
                }
            ) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception:
            return None

        if not info or info.get("_type") != "playlist":
            return None

        title = str(info.get("title", "Untitled Playlist"))
        entries: list = [e for e in (info.get("entries") or [])]
        count = int(info.get("playlist_count") or len(entries))
        return title, count, entries

    # ── interactive flow ────────────────────────────────────

    def _interactive_flow(self) -> None:
        """Gather all download options from CLI args or interactive prompts."""
        a = self.args
        c: dict = {}

        # ── URL or search query ──────────────────────────────
        c["is_playlist"] = False
        input_val: str | None = a.url.strip() if a.url else a.url

        if input_val is None:
            input_val = _ask(
                "text",
                f"{_NF_L}  Paste video URL or search:",
            ).ask()
            if input_val is None:
                raise KeyboardInterrupt()
            input_val = input_val.strip()

        if is_valid_url(input_val):
            c["url"] = input_val
        else:
            # Treat non-URL input as a YouTube search query
            resolved = self._search_youtube(input_val)
            if not resolved:
                raise KeyboardInterrupt()
            c["url"] = resolved

        # ── Playlist detection ──────────────────────────────
        if "list=" in c["url"]:
            pl_info = self._fetch_playlist_info(c["url"])
            if pl_info:
                pl_title, pl_count, pl_entries = pl_info
                self.console.print(
                    f"  {_NF_PL}  [yellow]Playlist detected:[/yellow]"
                    f" {pl_title}  [dim]({pl_count} items)[/dim]"
                )
                dl_all = _ask(
                    "confirm",
                    f"Download entire playlist?",
                    default=False,
                ).ask()
                if dl_all:
                    c["is_playlist"] = True
                    c["playlist_entries"] = pl_entries
                    c["playlist_title"] = pl_title
                if dl_all is None:
                    raise KeyboardInterrupt()

        # ── Format ──────────────────────────────────────────
        fmt_labels = [
            f"{_NF}  Video (MP4)",
            f"{_NF_A}  Audio (MP3)",
        ]
        fmt_map = {l: "mp4" if "MP4" in l else "mp3" for l in fmt_labels}
        if a.format is not None:
            c["format"] = "mp3" if a.format == "mp3" else "mp4"
        else:
            # Pre-select based on config default_format
            fmt_default = (
                fmt_labels[0]
                if self.settings.get("default_format", "video") != "audio"
                else fmt_labels[1]
            )
            fmt = _ask(
                "select",
                f"{_NF_D}  Select format:",
                choices=fmt_labels,
                default=fmt_default,
            ).ask()
            if fmt is None:
                raise KeyboardInterrupt()
            c["format"] = fmt_map[fmt]

        c["is_audio"] = c["format"] == "mp3"

        # ── Quality (video only) ────────────────────────────
        c["quality"] = "Best"
        qmap = {
            "best": "Best Quality",
            "2160p": "2160p (4K)",
            "1080p": "1080p (Full HD)",
            "720p": "720p (HD)",
            "480p": "480p",
        }
        if not c["is_audio"]:
            quality_choices = list(qmap.values())
            if a.quality is not None:
                c["quality"] = qmap.get(a.quality, "Best Quality")
            else:
                # Pre-select based on config default_quality
                q_default = qmap.get(
                    self.settings.get("default_quality", "best"), "Best Quality"
                )
                q = _ask(
                    "select",
                    f"{_NF}  Select quality:",
                    choices=quality_choices,
                    default=q_default,
                ).ask()
                if q is None:
                    raise KeyboardInterrupt()
                c["quality"] = q

        # ── Trim ─────────────────────────────────────────────
        c["trim_start"] = None
        c["trim_end"] = None

        if a.trim_start is not None or a.trim_end is not None:
            ts = a.trim_start or ""
            te = a.trim_end or ""
            if ts and parse_time(ts) is None:
                self._yellow("Invalid --trim-start.  Using no start trim.")
                ts = ""
            if te and parse_time(te) is None:
                self._yellow("Invalid --trim-end.  Using no end trim.")
                te = ""
            c["trim_start"] = ts if ts else None
            c["trim_end"] = te if te else None
        else:
            trim_label = "Trim audio?" if c["is_audio"] else "Trim video?"
            trim_q = _ask(
                "confirm",
                f"{_NF_S}  {trim_label}",
                default=False,
            ).ask()
            if trim_q is None:
                raise KeyboardInterrupt()
            if trim_q:
                ts = _ask(
                    "text",
                    "  Start time (HH:MM:SS, default 00:00:00):",
                    validate=lambda v: (
                        not v or parse_time(v) is not None or "Invalid time format."
                    ),
                ).ask()
                if ts is None:
                    raise KeyboardInterrupt()
                te = _ask(
                    "text",
                    "  End time (HH:MM:SS, press Enter to skip):",
                    validate=lambda v: (
                        not v or parse_time(v) is not None or "Invalid time format."
                    ),
                ).ask()
                if te is None:
                    raise KeyboardInterrupt()
                c["trim_start"] = ts.strip() if ts.strip() else None
                c["trim_end"] = te.strip() if te.strip() else None

        # ── Subtitles (video only) ─────────────────────────
        c["subs"] = False
        if a.subs:
            c["subs"] = True
        elif not c["is_audio"]:
            subs_q = _ask(
                "confirm",
                f"{_NF_B}  Embed subtitles (if available)?",
                default=False,
            ).ask()
            if subs_q is None:
                raise KeyboardInterrupt()
            c["subs"] = subs_q

        # ── Output directory ────────────────────────────────
        if a.output:
            c["output_dir"] = os.path.expanduser(a.output)
        else:
            c["output_dir"] = self._get_output_dir()

        # ── Summary + confirmation ─────────────────────────
        if not self._all_flags_provided():
            self._show_summary(c)
            proceed = _ask(
                "confirm",
                "Proceed with download?",
                default=True,
            ).ask()
            if not proceed:
                self._dim("Aborted.")
                sys.exit(0)

        self.config = c

    # ── output directory with PathCompleter ─────────────────

    def _get_output_dir(self) -> str:
        """Prompt for output directory with TAB path autocompletion.

        First Enter accepts the highlighted completion; second Enter submits.
        """
        kb = KeyBindings()

        @kb.add("enter")
        def _handle_enter(event) -> None:
            b = event.app.current_buffer
            if b.complete_state:
                # Completion menu is open → accept the highlighted item
                b.complete_state = None
            else:
                # No menu → submit
                b.validate_and_handle()

        default_dir = self.settings.get("output_dir", DEFAULT_OUTPUT_DIR)
        self.console.print(f"  {_NF_F}  [bold]Output folder:[/bold]")
        result = pt_prompt(
            "    ",
            completer=PathCompleter(only_directories=True),
            default=default_dir,
            style=None,
            key_bindings=kb,
        )
        self.console.print()
        return os.path.expanduser(result.strip() or default_dir)

    # ── flags check ─────────────────────────────────────────

    def _all_flags_provided(self) -> bool:
        a = self.args
        return bool(
            a.url
            and a.format is not None
            and (a.format == "mp3" or a.quality is not None)
        )

    # ── summary ─────────────────────────────────────────────

    def _show_summary(self, c: dict) -> None:
        """Print a minimal one-line-per-field summary."""
        fmt_label = "Audio" if c["is_audio"] else "Video"
        fmt_detail = "MP3" if c["is_audio"] else f"MP4  \u00b7  {c['quality']}"

        lines = [
            (f"{_NF_L}", "URL", c["url"]),
            (f"{_NF_D}", "Format", f"{fmt_label}  {fmt_detail}"),
        ]

        if c.get("is_playlist"):
            pl_title = c.get("playlist_title", "Playlist")
            pl_count = len(c.get("playlist_entries") or [])
            lines.append(
                (f"{_NF_PL}", "Playlist", f"{pl_title}  [dim]({pl_count} items)[/dim]")
            )

        if c.get("trim_start") or c.get("trim_end"):
            ts = c["trim_start"] or "\u2014"
            te = c["trim_end"] or "\u2014"
            lines.append((f"{_NF_S}", "Trim", f"{ts}  \u2192  {te}"))

        if c.get("subs"):
            lines.append((f"{_NF_B}", "Subs", "Yes"))

        lines.append((f"{_NF_F}", "Output", c["output_dir"]))

        self.console.print()
        for icon, label, value in lines:
            self.console.print(f"  {icon}  [dim]{label}[/dim]   {value}")
        self.console.print()

    # ── yt-dlp options ─────────────────────────────────────

    def _build_ydl_opts(self, output_dir: str) -> dict:
        is_audio = self.config["is_audio"]
        quality = self.config["quality"]
        subs = self.config["subs"]

        os.makedirs(output_dir, exist_ok=True)

        ydl_opts: dict = {
            "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "no_playlist": True,
            "ignore_errors": False,
            # Feature 5: Skip already-downloaded videos
            "download_archive": os.path.join(self._get_config_dir(), "archive.txt"),
        }

        if is_audio:
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                },
            ]
        else:
            qkey = (
                quality.replace(" (4K)", "")
                .replace(" (Full HD)", "")
                .replace(" (HD)", "")
            )
            fmt = FORMAT_VIDEO_QUALITY.get(qkey, FORMAT_VIDEO_QUALITY["Best"])
            ydl_opts["format"] = fmt
            ydl_opts["merge_output_format"] = "mp4"
            ydl_opts["postprocessor_args"] = {
                "ffmpeg": ["-movflags", "+faststart"],
            }
            ydl_opts["postprocessors"] = []

            if subs:
                ydl_opts["writesubtitles"] = True
                ydl_opts["writeautomaticsub"] = True
                ydl_opts["subtitlesformat"] = "srt"
                ydl_opts["embedsubs"] = True
                ydl_opts["postprocessors"].append({"key": "FFmpegEmbedSubtitle"})

        return ydl_opts

    # ── execute download (dispatcher) ────────────────────

    def _execute_download(self) -> None:
        """Dispatch: single video or playlist."""
        if self.config.get("is_playlist"):
            self._download_playlist()
        else:
            path = self._download_single()
            if path is None:
                raise DownloadError(self._last_error or "Download failed")
            self.last_output_path = path

    # ── single-video download ───────────────────────────

    def _download_single(self, display_title: str | None = None) -> str | None:
        """Download one video with progress bar + spinner.

        Returns the output file path on success, or ``None`` on error.
        The error message is stored in ``self._last_error``.
        """
        c = self.config
        ydl_opts = self._build_ydl_opts(c["output_dir"])

        progress_queue: queue.Queue = queue.Queue()
        thread = DownloadThread(c["url"], ydl_opts, progress_queue)
        thread.start()

        output_path: str | None = None
        error_msg: str | None = None
        total_bytes: int = 0
        needs_processing: bool = False

        desc = display_title or os.path.basename(ydl_opts["outtmpl"]).replace(
            "%(title)s.%(ext)s", "video"
        )

        # ── Phase 1: Download with live progress bar ────────────
        progress = Progress(
            TextColumn("[bold cyan]{task.description:15.15s}"),
            BarColumn(bar_width=32),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            DownloadColumn(binary_units=True),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=self.console,
            transient=True,
        )

        with progress:
            task_id = progress.add_task(f"{_NF_D}  {desc}", total=None)

            while thread.is_alive() or not progress_queue.empty():
                try:
                    data = progress_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if data["status"] == "downloading":
                    total_bytes = data.get("total", 0) or total_bytes
                    dloaded = data.get("downloaded", 0)
                    if total_bytes and progress._tasks[task_id].total is None:
                        progress.update(task_id, total=total_bytes)
                    progress.update(
                        task_id,
                        completed=dloaded,
                        description=f"{_NF_D}  {desc}",
                    )

                elif data["status"] == "post_processing":
                    needs_processing = True
                    break

                elif data["status"] == "completed":
                    output_path = data.get("output_path", "")
                    progress.update(
                        task_id,
                        description=f"{_NF_C}  Complete!",
                        completed=total_bytes or 100,
                    )
                    break

                elif data["status"] == "error":
                    error_msg = data.get("message", "Unknown error")
                    progress.update(
                        task_id,
                        description=f"{_NF_X}  Error",
                    )
                    break

        # ── Phase 2: Post-processing spinner ───────────────────
        if needs_processing and error_msg is None:
            if c["is_audio"]:
                spin_msg = f"{_NF_G}  Converting to MP3 via FFmpeg\u2026"
            elif c.get("trim_start") or c.get("trim_end"):
                spin_msg = f"{_NF_G}  Muxing & trimming via FFmpeg (stream copy)\u2026"
            else:
                spin_msg = f"{_NF_G}  Muxing video & audio streams via FFmpeg\u2026"

            with self.console.status(f"[bold cyan]{spin_msg}", spinner="dots"):
                while thread.is_alive() or not progress_queue.empty():
                    try:
                        data = progress_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    if data["status"] == "completed":
                        output_path = data.get("output_path", "")
                        break

                    elif data["status"] == "error":
                        error_msg = data.get("message", "Unknown error")
                        break

        # ── Handle result ──────────────────────────────────────
        if error_msg:
            self._last_error = error_msg
            self.console.print(f"\n  [red]{_NF_X}  {error_msg}[/red]\n")
            return None

        if not output_path or not os.path.isfile(output_path):
            self._yellow("Download may have completed but file not found.")
            return None

        self.console.print()

        # ── Trim ───────────────────────────────────────────────
        if c.get("trim_start") or c.get("trim_end"):
            trimmed = self._run_trim(output_path)
            if trimmed and os.path.isfile(trimmed):
                output_path = trimmed

        return output_path

    # ── playlist download ──────────────────────────────

    def _download_playlist(self) -> None:
        """Download every entry in the playlist sequentially."""
        c = self.config
        entries: list = c.get("playlist_entries", [])
        total = len(entries)
        completed = 0
        failed = 0
        last_path: str | None = None

        self.console.print(
            f"  {_NF_PL}  [bold]Playlist:[/bold] {c.get('playlist_title', 'Untitled')}"
            f"  [dim]({total} items)[/dim]"
        )
        self.console.print()

        for i, entry in enumerate(entries, 1):
            title = entry.get("title") or f"video {i}"
            video_url = entry.get("url") or entry.get("webpage_url") or ""
            if not video_url:
                self._yellow(f'[{i}/{total}] Skipping "{title}" \u2014  no URL.')
                failed += 1
                continue

            c["url"] = video_url
            label = f"[{i}/{total}] {title}"

            path = self._download_single(display_title=label)
            if path:
                completed += 1
                last_path = path
            else:
                failed += 1
                self._yellow(f"[{i}/{total}] Failed — continuing to next item.")

        self.last_output_path = last_path or ""
        self.console.print()
        if failed:
            self._yellow(f"Playlist done: {completed} downloaded, {failed} failed.")
        else:
            self._green(f"Playlist complete: all {completed} items downloaded.")

        # Feature 6: Desktop notification for playlist
        pl_title = c.get("playlist_title", "Playlist")
        if completed > 0:
            self._send_notification(
                "YVid Download Complete",
                f"{completed} items from playlist {pl_title}",
            )

    # ── trim ───────────────────────────────────────────────

    def _run_trim(self, input_path: str) -> str | None:
        """Trim media with FFmpeg using a temp file (Windows-safe)."""
        if not input_path or not os.path.isfile(input_path):
            return None

        start_raw = self.config.get("trim_start", "") or ""
        end_raw = self.config.get("trim_end", "") or ""

        if not start_raw and not end_raw:
            return input_path

        ext = os.path.splitext(input_path)[1].lower()
        if ext not in (
            ".mp4",
            ".mkv",
            ".webm",
            ".mov",
            ".avi",
            ".mp3",
            ".m4a",
            ".ogg",
            ".opus",
            ".flac",
            ".wav",
            ".aac",
        ):
            return input_path

        if not shutil.which("ffmpeg"):
            self._yellow("FFmpeg not found.  Skipping trim.")
            return input_path

        if start_raw and parse_time(start_raw) is None:
            self._yellow("Invalid start time.  Skipping trim.")
            return input_path
        if end_raw and parse_time(end_raw) is None:
            self._yellow("Invalid end time.  Skipping trim.")
            return input_path

        self._dim(f"{_NF_S}  Trimming\u2026")

        # Write to a temp file first to avoid Windows file-locking issues
        tmp_path = input_path + ".yvid-trim.tmp"
        cmd = ["ffmpeg", "-y"]
        if start_raw:
            cmd.extend(["-ss", start_raw])
        cmd.extend(["-i", input_path])
        if end_raw:
            cmd.extend(["-to", end_raw])
        cmd.extend(["-c", "copy", tmp_path])

        proc: subprocess.Popen | None = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            _, stderr_data = proc.communicate(timeout=300)

            if proc.returncode != 0:
                err_tail = stderr_data.decode("utf-8", errors="replace")[-200:].strip()
                self._yellow(f"Trim failed: {err_tail}")
                _safe_remove(tmp_path)
                return input_path

            if not os.path.isfile(tmp_path) or os.path.getsize(tmp_path) == 0:
                self._yellow("Trim produced empty file.  Keeping original.")
                _safe_remove(tmp_path)
                return input_path

            # Swap temp → original (atomic on POSIX, works on Windows)
            os.replace(tmp_path, input_path)
            self._green("Trim complete.")
            return input_path

        except subprocess.TimeoutExpired:
            if proc is not None:
                proc.kill()
            _safe_remove(tmp_path)
            self._yellow("Trim timed out (5 min).  Keeping original.")
            return input_path
        except Exception as exc:
            _safe_remove(tmp_path)
            self._yellow(f"Trim error: {exc}")
            return input_path

    # ── completion screen ───────────────────────────────────

    def _show_completion(self) -> None:
        """Print a one-line download-complete status + desktop notification."""
        path = getattr(self, "last_output_path", "")
        if not path or not os.path.isfile(path):
            return

        filename = os.path.basename(path)
        saved_dir = os.path.dirname(path)
        short_dir = saved_dir.replace(os.path.expanduser("~"), "~")
        file_size = format_bytes(os.path.getsize(path))

        self.console.print(
            f"  {_NF_C}  [green]Download complete[/green]  \u2014  "
            f"[bold]{filename}[/bold]  [dim]({file_size})[/dim]"
        )
        self._dim(f"      {short_dir}/")

        if self.config.get("trim_start") or self.config.get("trim_end"):
            ts = self.config.get("trim_start") or "0:00"
            te = self.config.get("trim_end") or "end"
            self._dim(f"      {_NF_S}  Trimmed: {ts}  \u2192  {te}")

        # Feature 6: Desktop notification
        self._send_notification(
            "YVid Download Complete",
            f"Successfully downloaded {filename}",
        )

        self.console.print()

    # ── desktop notification (Feature 6) ─────────────────────

    @staticmethod
    def _send_notification(title: str, message: str) -> None:
        """Show a native desktop notification.

        - **Linux**: ``notify-send`` (libnotify)
        - **macOS**: ``osascript`` (AppleScript native banner)
        - **Windows**: PowerShell Windows Runtime toast API

        Gracefully swallows any failure (missing tool, timeout, etc.).
        """
        try:
            if sys.platform == "linux":
                subprocess.run(
                    ["notify-send", title, message],
                    timeout=5,
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
            elif sys.platform == "darwin":
                # macOS native banner via AppleScript
                script = f'display notification "{message}" with title "{title}"'
                subprocess.run(
                    ["osascript", "-e", script],
                    timeout=5,
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
            elif sys.platform == "win32":
                # Windows Toast via PowerShell Runtime API
                ps_script = (
                    f"[Windows.UI.Notifications.ToastNotificationManager,"
                    f" Windows.UI.Notifications,"
                    f" ContentType=WindowsRuntime] | Out-Null;"
                    f" $template = [Windows.UI.Notifications"
                    f" ::ToastNotificationManager]"
                    f" ::GetTemplateContent("
                    f" [Windows.UI.Notifications.ToastTemplateType]"
                    f" ::ToastText02);"
                    f' $textNodes = $template.GetElementsByTagName("text");'
                    f" $textNodes.Item(0).AppendChild("
                    f' $template.CreateTextNode("{title}")) | Out-Null;'
                    f" $textNodes.Item(1).AppendChild("
                    f' $template.CreateTextNode("{message}")) | Out-Null;'
                    f" $toast = [Windows.UI.Notifications"
                    f" ::ToastNotification]::new($template);"
                    f" [Windows.UI.Notifications"
                    f" ::ToastNotificationManager]"
                    f" ::CreateToastNotifier().Show($toast)"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", ps_script],
                    timeout=10,
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
        except Exception:
            pass  # Swallow all errors — not critical

    # ── download another? ───────────────────────────────────

    def _ask_download_another(self) -> bool:
        """Prompt the user to download another video."""
        again = _ask(
            "confirm",
            f"{_NF_D}  Download another video?",
            default=False,
        ).ask()
        if again is None:
            return False
        return again

    # ── error handling ─────────────────────────────────────

    def _handle_download_error(self, exc: DownloadError) -> bool:
        """Handle a download error.  Returns True if caller should retry."""
        msg = str(exc)
        self.console.print(f"\n  [red]{_NF_X}  {msg}[/red]\n")

        if "403" in msg or "age-restricted" in msg or "private" in msg.lower():
            if self._try_update_ytdlp():
                self._green("Ready to retry.")
                return True

        choice = _ask("confirm", "Retry?", default=False).ask()
        return bool(choice)

    def _try_update_ytdlp(self) -> bool:
        """Attempt to upgrade yt-dlp via pip.  Returns True on success."""
        self._yellow(f"{_NF_R}  Attempting to update yt-dlp\u2026")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                self._green("yt-dlp updated successfully!")
                return True
            self._yellow(f"Update failed: {result.stderr.strip()}")
        except Exception as exc:
            self._yellow(f"Update error: {exc}")
        return False


# ═══════════════════════════════════════════════════════════════
#  EXCEPTIONS
# ═══════════════════════════════════════════════════════════════


class DownloadError(Exception):
    """Raised when yt-dlp reports a download failure."""


# ═══════════════════════════════════════════════════════════════
#  CLI ARGUMENTS
# ═══════════════════════════════════════════════════════════════


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="yvid",
        description="Modern Terminal Video Downloader",
        epilog="Run without arguments for interactive mode.",
    )
    parser.add_argument(
        "--url",
        help="Video URL to download",
    )
    parser.add_argument(
        "--format",
        choices=["mp4", "mp3"],
        default=None,
        help="Output format (default: prompt in interactive mode)",
    )
    parser.add_argument(
        "--quality",
        choices=["best", "2160p", "1080p", "720p", "480p"],
        default=None,
        help="Video quality (video only, default: best)",
    )
    parser.add_argument(
        "--trim-start",
        help="Trim start time (HH:MM:SS or SS)",
    )
    parser.add_argument(
        "--trim-end",
        help="Trim end time (HH:MM:SS or SS)",
    )
    parser.add_argument(
        "--subs",
        action="store_true",
        help="Download subtitles when available",
    )
    parser.add_argument(
        "--output",
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    return parser.parse_args(argv)


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════


def main() -> None:
    # Enable ANSI escape sequence support on Windows legacy consoles
    colorama.just_fix_windows_console()
    args = parse_args()
    cli = YVidCLI(args)
    cli.run()


if __name__ == "__main__":
    main()
