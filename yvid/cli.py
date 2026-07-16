#!/usr/bin/env python3
"""
YVid-CLI — Modern Terminal Video Downloader

Built with yt-dlp + Rich + Questionary.
Shared core logic lives under ``core/``.

Usage:
    yvid                   Interactive TUI
    yvid --url <URL>       Hybrid — prompts for missing options
    yvid --url <URL> --format mp4 --quality 1080p  Direct download
"""

from __future__ import annotations

import argparse
import os
import queue
import shutil
import subprocess
import sys

import questionary
import yt_dlp
from questionary import Style as QStyle
from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.text import Text

from .core.config import (
    APP_NAME,
    VERSION,
    DEFAULT_OUTPUT_DIR,
    FORMAT_VIDEO_QUALITY,
)
from .core.helpers import (
    format_bytes,
    format_eta,
    format_error_message,
    is_valid_url,
    parse_time,
)
from .core.download_thread import DownloadThread


# ═══════════════════════════════════════════════════════════════
#  QUESTIONARY STYLING
# ═══════════════════════════════════════════════════════════════

QUESTIONARY_STYLE = QStyle(
    [
        ("qmark", "bold fg:cyan"),
        ("question", "bold fg:white"),
        ("answer", "fg:green bold"),
        ("pointer", "bold fg:cyan"),
        ("highlighted", "bold fg:cyan"),
        ("selected", "fg:green"),
        ("separator", "fg:gray"),
        ("instruction", "fg:gray italic"),
        ("text", ""),
        ("disabled", "fg:gray"),
    ]
)


# ═══════════════════════════════════════════════════════════════
#  MAIN CLI APPLICATION
# ═══════════════════════════════════════════════════════════════


class YVidCLI:
    """The YVid-CLI interactive terminal application."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.console = Console()
        self.config: dict = {}
        self.last_output_path: str = ""

    # ── public entry point ─────────────────────────────

    def run(self) -> None:
        """Main entry point. Retries once on 403 / update."""
        while True:
            try:
                self._show_banner()
                self._interactive_flow()
                self._execute_download()
            except DownloadError as exc:
                if self._handle_download_error(exc):
                    continue  # retry (yt-dlp updated)
                sys.exit(1)
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Cancelled.[/yellow]")
                sys.exit(0)
            except Exception as exc:
                self.console.print(
                    Panel(
                        f"[red bold]Unexpected error:[/red bold]\n{exc}",
                        border_style="red",
                    )
                )
                sys.exit(1)
            break  # success

    # ── banner ─────────────────────────────────────────

    def _show_banner(self) -> None:
        self.console.clear()
        title = Text()
        title.append("YVid", style="bold bright_magenta")
        title.append("-", style="bold magenta")
        title.append("CLI", style="bold cyan")
        subtitle = Text.assemble(
            ("Terminal Video Downloader", "cyan"),
            "\n",
            ("v" + VERSION, "bright_black italic"),
        )
        panel = Panel(
            Align.center(Text.assemble(title, "\n", subtitle)),
            border_style="bright_blue",
            box=box.ROUNDED,
            padding=(1, 4),
            title="[bold]Welcome[/bold]",
        )
        self.console.print(panel)
        self.console.print()

    # ── interactive configuration flow ─────────────────

    def _interactive_flow(self) -> None:
        """Gather all download options from CLI args or interactive prompts."""
        a = self.args
        c: dict = {}

        # ── URL ──
        if a.url and is_valid_url(a.url):
            c["url"] = a.url.strip()
        else:
            url = questionary.text(
                "Paste video URL:",
                validate=lambda val: is_valid_url(val) or "Invalid URL.",
                style=QUESTIONARY_STYLE,
            ).ask()
            if url is None:
                raise KeyboardInterrupt()
            c["url"] = url.strip()

        # ── Format ──
        fmt_choices = ["\U0001f3a5  Video (MP4)", "\U0001f3b5  Audio (MP3)"]
        if a.format is not None:
            c["format"] = "mp3" if a.format == "mp3" else "mp4"
        else:
            fmt = questionary.select(
                "Select format:",
                choices=fmt_choices,
                style=QUESTIONARY_STYLE,
            ).ask()
            if fmt is None:
                raise KeyboardInterrupt()
            c["format"] = "mp3" if "MP3" in fmt else "mp4"

        c["is_audio"] = c["format"] == "mp3"

        # ── Quality (video only) ──
        c["quality"] = "Best"
        if not c["is_audio"]:
            quality_choices = [
                "Best Quality",
                "2160p (4K)",
                "1080p (Full HD)",
                "720p (HD)",
                "480p",
            ]
            if a.quality is not None:
                # Map CLI values to display values
                qmap = {
                    "best": "Best Quality",
                    "2160p": "2160p (4K)",
                    "1080p": "1080p (Full HD)",
                    "720p": "720p (HD)",
                    "480p": "480p",
                }
                c["quality"] = qmap.get(a.quality, "Best Quality")
            else:
                q = questionary.select(
                    "Select quality:",
                    choices=quality_choices,
                    default="Best Quality",
                    style=QUESTIONARY_STYLE,
                ).ask()
                if q is None:
                    raise KeyboardInterrupt()
                c["quality"] = q

        # ── Trim ──
        c["trim_start"] = None
        c["trim_end"] = None

        if a.trim_start is not None or a.trim_end is not None:
            # From CLI flags
            ts = a.trim_start or ""
            te = a.trim_end or ""
            if ts and parse_time(ts) is None:
                self.console.print(
                    "[red]Invalid --trim-start. Using no start trim.[/red]"
                )
                ts = ""
            if te and parse_time(te) is None:
                self.console.print("[red]Invalid --trim-end. Using no end trim.[/red]")
                te = ""
            c["trim_start"] = ts if ts else None
            c["trim_end"] = te if te else None
        elif not c["is_audio"]:
            trim_q = questionary.confirm(
                "Cut / trim the video?",
                default=False,
                style=QUESTIONARY_STYLE,
            ).ask()
            if trim_q is None:
                raise KeyboardInterrupt()
            if trim_q:
                ts = questionary.text(
                    "Start time (HH:MM:SS or SS):",
                    validate=lambda v: (
                        not v or parse_time(v) is not None or "Invalid time format."
                    ),
                    style=QUESTIONARY_STYLE,
                ).ask()
                if ts is None:
                    raise KeyboardInterrupt()
                te = questionary.text(
                    "End time (HH:MM:SS or SS):",
                    validate=lambda v: (
                        not v or parse_time(v) is not None or "Invalid time format."
                    ),
                    style=QUESTIONARY_STYLE,
                ).ask()
                if te is None:
                    raise KeyboardInterrupt()
                c["trim_start"] = ts.strip() if ts.strip() else None
                c["trim_end"] = te.strip() if te.strip() else None

        # ── Subtitles (video only) ──
        c["subs"] = False
        if a.subs:
            c["subs"] = True
        elif not c["is_audio"]:
            subs_q = questionary.confirm(
                "Embed subtitles (if available)?",
                default=False,
                style=QUESTIONARY_STYLE,
            ).ask()
            if subs_q is None:
                raise KeyboardInterrupt()
            c["subs"] = subs_q

        # ── Output directory ──
        if a.output:
            c["output_dir"] = os.path.expanduser(a.output)
        else:
            out = questionary.text(
                "Output folder:",
                default=DEFAULT_OUTPUT_DIR,
                style=QUESTIONARY_STYLE,
            ).ask()
            if out is None:
                raise KeyboardInterrupt()
            c["output_dir"] = os.path.expanduser(out.strip() or DEFAULT_OUTPUT_DIR)

        # ── Summary confirmation ──
        if not self._all_flags_provided():
            self._show_summary(c)
            proceed = questionary.confirm(
                "Proceed with download?",
                default=True,
                style=QUESTIONARY_STYLE,
            ).ask()
            if not proceed:
                self.console.print("[yellow]Aborted.[/yellow]")
                sys.exit(0)

        self.config = c

    def _all_flags_provided(self) -> bool:
        """Return True when the user supplied enough CLI flags to skip prompts."""
        a = self.args
        # If every flag that has a default is set, we consider it "all provided"
        return bool(
            a.url
            and a.format is not None
            and (a.format == "mp3" or a.quality is not None)
        )

    def _show_summary(self, c: dict) -> None:
        """Display a confirmation summary before downloading."""
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bright_black", justify="right")
        table.add_column(style="white")

        fmt_display = "Audio MP3" if c["is_audio"] else "Video MP4"
        quality_display = ""
        if not c["is_audio"]:
            quality_display = f" \u00b7 {c['quality']}"

        trim_display = ""
        if c["trim_start"] or c["trim_end"]:
            ts = c["trim_start"] or "\u2014"
            te = c["trim_end"] or "\u2014"
            trim_display = f"\n       {ts}  \u2192  {te}"

        table.add_row("URL", c["url"])
        table.add_row("Format", f"{fmt_display}{quality_display}")
        if trim_display:
            table.add_row("Trim", trim_display)
        table.add_row("Output", c["output_dir"])

        self.console.print(
            Panel(
                table,
                title="[bold]Summary[/bold]",
                border_style="cyan",
                box=box.ROUNDED,
            )
        )
        self.console.print()

    # ── yt-dlp options ─────────────────────────────────

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
            # Map display name to format key
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

    # ── execute download ──────────────────────────────

    def _execute_download(self) -> None:
        """Start the download thread and render progress with Rich."""
        c = self.config
        ydl_opts = self._build_ydl_opts(c["output_dir"])

        progress_queue: queue.Queue = queue.Queue()
        thread = DownloadThread(c["url"], ydl_opts, progress_queue)
        thread.start()

        output_path: str | None = None
        error_msg: str | None = None
        total_bytes: int = 0

        # Derive a short display filename from outtmpl template
        short_filename = os.path.basename(ydl_opts["outtmpl"]).replace(
            "%(title)s.%(ext)s", "video"
        )

        progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            DownloadColumn(binary_units=True),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=self.console,
            transient=True,
        )

        with progress:
            task_id = progress.add_task("[bold]Connecting...", total=None)

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
                        description=f"[bold]{short_filename}[/bold]",
                    )

                elif data["status"] == "post_processing":
                    progress.update(
                        task_id,
                        description="[yellow]Processing...",
                    )

                elif data["status"] == "completed":
                    output_path = data.get("output_path", "")
                    progress.update(
                        task_id,
                        description="[green]Complete!",
                        completed=total_bytes or 100,
                    )
                    break

                elif data["status"] == "error":
                    error_msg = data.get("message", "Unknown error")
                    progress.update(
                        task_id,
                        description="[red]Error!",
                    )
                    break

        # ── Handle result ──
        if error_msg:
            raise DownloadError(error_msg)

        if not output_path or not os.path.isfile(output_path):
            self.console.print(
                "[yellow]Download may have completed but file not found.[/yellow]"
            )
            return

        self.console.print()  # spacing

        # ── Trim ──
        if self.config.get("trim_start") or self.config.get("trim_end"):
            trimmed = self._run_trim(output_path)
            if trimmed and os.path.isfile(trimmed):
                output_path = trimmed

        self.last_output_path = output_path
        self._show_completion(output_path)

    # ── trim ──────────────────────────────────────────

    def _run_trim(self, input_path: str) -> str | None:
        """Trim the video with FFmpeg stream copy. Replaces file in-place."""
        if not input_path or not os.path.isfile(input_path):
            return None

        start_raw = self.config.get("trim_start", "") or ""
        end_raw = self.config.get("trim_end", "") or ""

        if not start_raw and not end_raw:
            return input_path

        ext = os.path.splitext(input_path)[1].lower()
        if ext not in (".mp4", ".mkv", ".webm", ".mov", ".avi"):
            return input_path

        if not shutil.which("ffmpeg"):
            self.console.print("[yellow]FFmpeg not found. Skipping trim.[/yellow]")
            return input_path

        # Validate times (they were already validated during input, but double-check)
        if start_raw:
            p = parse_time(start_raw)
            if p is None:
                self.console.print(
                    "[yellow]Invalid start time. Skipping trim.[/yellow]"
                )
                return input_path
        if end_raw:
            p = parse_time(end_raw)
            if p is None:
                self.console.print("[yellow]Invalid end time. Skipping trim.[/yellow]")
                return input_path

        self.console.print("[cyan]Trimming video (stream copy)...[/cyan]")

        cmd = ["ffmpeg", "-y"]
        if start_raw:
            cmd.extend(["-ss", start_raw])
        cmd.extend(["-i", input_path])
        if end_raw:
            cmd.extend(["-to", end_raw])
        cmd.extend(["-c", "copy", input_path])

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
                self.console.print(f"[red]Trim failed: {err_tail}[/red]")
                return input_path

            if not os.path.isfile(input_path) or os.path.getsize(input_path) == 0:
                self.console.print(
                    "[red]Trim produced empty file. Keeping original.[/red]"
                )
                return input_path

            self.console.print("[green]Trim complete.[/green]")
            return input_path

        except subprocess.TimeoutExpired:
            if proc is not None:
                proc.kill()
            self.console.print("[red]Trim timed out (5 min). Keeping original.[/red]")
            return input_path
        except Exception as exc:
            self.console.print(f"[red]Trim error: {exc}[/red]")
            return input_path

    # ── completion screen ─────────────────────────────

    def _show_completion(self, filepath: str) -> None:
        """Show a styled completion screen with action choices."""
        if not filepath or not os.path.isfile(filepath):
            return

        filename = os.path.basename(filepath)
        saved_dir = os.path.dirname(filepath)
        short_dir = saved_dir.replace(os.path.expanduser("~"), "~")
        file_size = format_bytes(os.path.getsize(filepath))

        info_lines = Text.assemble(
            ("\U0001f4c2  ", "bright_black"),
            (f"{short_dir}/", "bright_black"),
            (f"{filename}", "white bold"),
            "\n",
            ("\U0001f4c1  ", "bright_black"),
            (f"{file_size}", "cyan"),
        )

        if self.config.get("trim_start") or self.config.get("trim_end"):
            ts = self.config.get("trim_start") or "0:00"
            te = self.config.get("trim_end") or "end"
            info_lines.append("\n")
            info_lines.append("\u2702  ", style="bright_black")
            info_lines.append(f"Trimmed: {ts}  \u2192  {te}", style="bright_black")

        panel = Panel(
            Align.center(info_lines),
            title="[bold green]\u2714  Download Complete[/bold green]",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 2),
        )
        self.console.print(panel)
        self.console.print()

        # Action menu
        action = questionary.select(
            "What now?",
            choices=[
                "\u25b6  Play with mpv",
                "\U0001f4c2  Open containing folder",
                "\u274c  Quit",
            ],
            style=QUESTIONARY_STYLE,
        ).ask()

        if action is None:
            return

        if "Play" in action:
            self._play_video(filepath)
        elif "Open" in action:
            self._open_folder(saved_dir)
        # else Quit — just exit

    # ── media actions ─────────────────────────────────

    def _play_video(self, path: str) -> None:
        """Open the file with mpv or the system default player."""
        try:
            if shutil.which("mpv"):
                subprocess.Popen(
                    ["mpv", path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            self.console.print("[yellow]Could not open media player.[/yellow]")

    def _open_folder(self, directory: str) -> None:
        """Open the file manager at the given directory."""
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", directory])
            elif sys.platform == "win32":
                os.startfile(directory)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", directory])
        except Exception:
            self.console.print("[yellow]Could not open file manager.[/yellow]")

    # ── error handling ────────────────────────────────

    def _handle_download_error(self, exc: DownloadError) -> bool:
        """Handle a download error. Returns True if caller should retry."""
        msg = str(exc)

        self.console.print(
            Panel(
                f"[red bold]\u2716  Download failed[/red bold]\n\n{msg}",
                border_style="red",
                box=box.ROUNDED,
            )
        )
        self.console.print()

        # 403 / restriction → auto-update yt-dlp and retry
        if "403" in msg or "age-restricted" in msg or "private" in msg.lower():
            if self._try_update_ytdlp():
                self.console.print("[green]Ready to retry.[/green]")
                return True

        choice = questionary.confirm(
            "Retry?",
            default=False,
            style=QUESTIONARY_STYLE,
        ).ask()
        return bool(choice)

    def _try_update_ytdlp(self) -> bool:
        """Attempt to upgrade yt-dlp via uv. Returns True on success."""
        self.console.print("[yellow]Attempting to update yt-dlp...[/yellow]")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                self.console.print("[green]yt-dlp updated successfully![/green]")
                return True
            self.console.print(f"[red]Update failed: {result.stderr.strip()}[/red]")
        except Exception as exc:
            self.console.print(f"[red]Update error: {exc}[/red]")
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
    args = parse_args()
    cli = YVidCLI(args)
    cli.run()


if __name__ == "__main__":
    main()
