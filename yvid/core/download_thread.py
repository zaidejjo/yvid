"""
Background download worker — runs yt-dlp in a daemon thread.

Shared by both the GUI (``app.py``) and CLI (``cli.py``) entry points.
"""

from __future__ import annotations

import os
import queue
import threading

import yt_dlp

from .helpers import format_error_message


class DownloadThread(threading.Thread):
    """Runs yt-dlp in a daemon thread and pushes progress updates to a queue.

    Queue messages
    --------------
    ``{"status": "downloading", "percent": float, "speed": float,
       "eta": float, "downloaded": int, "total": int}``
        Periodic progress update during the download phase.
    ``{"status": "post_processing"}``
        The raw download has finished; yt-dlp is now merging / converting.
    ``{"status": "completed", "output_path": str}``
        Everything is done and the final file path was resolved.
    ``{"status": "error", "message": str}``
        yt-dlp or the path resolver raised an exception.
    """

    def __init__(self, url: str, ydl_opts: dict, progress_queue: queue.Queue) -> None:
        super().__init__(daemon=True)
        self.url = url
        self.ydl_opts = ydl_opts
        self.queue = progress_queue
        self._original_filename: str | None = None

    # ── public ─────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self.ydl_opts["progress_hooks"] = [self._progress_hook]
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                ydl.download([self.url])

            output_path = self._resolve_output_path()
            self.queue.put({"status": "completed", "output_path": output_path})

        except Exception as exc:
            self.queue.put(
                {"status": "error", "message": format_error_message(str(exc))}
            )

    # ── internal ───────────────────────────────────────────────

    def _progress_hook(self, d: dict) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            percent = (downloaded / total * 100) if total > 0 else 0.0

            self.queue.put(
                {
                    "status": "downloading",
                    "percent": percent,
                    "speed": speed,
                    "eta": eta,
                    "downloaded": downloaded,
                    "total": total,
                }
            )

        elif d["status"] == "finished":
            self._original_filename = d.get("filename", "")
            self.queue.put({"status": "post_processing"})

    # ── path resolution ────────────────────────────────────────

    def _resolve_output_path(self) -> str:
        if not self._original_filename:
            return ""

        is_audio = any(
            pp.get("key") == "FFmpegExtractAudio"
            for pp in self.ydl_opts.get("postprocessors", [])
        )

        # The "finished" hook fires *before* post-processing (merge,
        # extract-audio, faststart).  We know the final extension.
        if is_audio:
            path = os.path.splitext(self._original_filename)[0] + ".mp3"
        else:
            path = self._original_filename

        if os.path.exists(path):
            return path

        # Fallback: scan the output directory for the newest media
        # file that is *not* a temp / part file.
        outdir = os.path.dirname(self.ydl_opts.get("outtmpl", ""))
        if outdir and os.path.isdir(outdir):
            VALID_EXTS = frozenset(
                {
                    ".mp4",
                    ".mkv",
                    ".webm",
                    ".mp3",
                    ".m4a",
                    ".ogg",
                    ".opus",
                    ".flac",
                    ".wav",
                    ".aac",
                }
            )
            try:
                candidates = [
                    os.path.join(outdir, f)
                    for f in os.listdir(outdir)
                    if (
                        os.path.splitext(f)[1].lower() in VALID_EXTS
                        and not f.endswith(".part")
                        and not f.endswith(".temp")
                    )
                ]
                if candidates:
                    best = max(candidates, key=os.path.getmtime)
                    if os.path.getsize(best) > 0:
                        return best
            except OSError:
                pass

        return path if os.path.exists(path) else ""
