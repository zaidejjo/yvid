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
            # Before running yt-dlp, check for stale download_archive
            # entries: if the archive says the video was downloaded but
            # the expected output file no longer exists, remove the
            # entry so yt-dlp actually re-downloads it.
            self._clean_stale_archive_entry()

            self.ydl_opts["progress_hooks"] = [self._progress_hook]
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                ydl.download([self.url])

                # yt-dlp's download_archive may cause an instant skip —
                # no progress hooks fire and _original_filename stays None.
                # Resolve the expected output path from video metadata.
                if not self._original_filename:
                    self._original_filename = self._resolve_archive_skip_path(ydl)

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

    def _get_expected_path(self) -> str:
        """Build the expected final output path from ``ydl_opts`` and
        video info, without relying on downloaded files.

        This is used by both the stale-archive check and the archive-skip
        path resolver.
        """
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if not info or info.get("_type") == "playlist":
                    return ""
                path: str = ydl.prepare_filename(info)  # type: ignore[no-untyped-call]
        except Exception:
            return ""

        merge_fmt = self.ydl_opts.get("merge_output_format")
        if merge_fmt:
            base, _ = os.path.splitext(path)
            path = f"{base}.{merge_fmt}"

        is_audio = any(
            pp.get("key") == "FFmpegExtractAudio"
            for pp in self.ydl_opts.get("postprocessors", [])
        )
        if is_audio:
            base, _ = os.path.splitext(path)
            path = f"{base}.mp3"

        return path

    def _clean_stale_archive_entry(self) -> None:
        """If ``download_archive`` marks this video as downloaded but
        the expected output file no longer exists, remove the stale
        archive entry so yt-dlp will re-download it.
        """
        archive_path: str | None = self.ydl_opts.get("download_archive")
        if not archive_path or not os.path.isfile(archive_path):
            return

        path = self._get_expected_path()
        if not path:
            return

        # File already exists — nothing stale
        if os.path.exists(path):
            return

        # Expected file is missing — remove the archive entry
        try:
            video_id = self._extract_video_id()
            if video_id:
                lines = []
                removed = False
                with open(archive_path) as f:
                    for line in f:
                        stripped = line.strip()
                        # Archive format: "extractor KEY" e.g. "youtube dQw4w9WgXcQ"
                        parts = stripped.split()
                        if len(parts) >= 2 and parts[-1] == video_id:
                            removed = True
                            continue
                        lines.append(stripped)
                if removed:
                    with open(archive_path, "w") as f:
                        f.write("\n".join(lines) + "\n")
        except Exception:
            pass

    def _extract_video_id(self) -> str | None:
        """Extract the YouTube video ID from the URL."""
        import urllib.parse

        try:
            parsed = urllib.parse.urlparse(self.url)
            if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
                if parsed.path == "/watch":
                    return urllib.parse.parse_qs(parsed.query).get("v", [None])[0]
                if parsed.netloc == "youtu.be":
                    return parsed.path.lstrip("/")
        except Exception:
            pass
        return None

    def _resolve_archive_skip_path(self, ydl: yt_dlp.YoutubeDL) -> str | None:
        """When ``download_archive`` causes yt-dlp to skip, determine
        the expected output path from video metadata.

        Returns the merged / final path, or ``None`` on failure.
        """
        try:
            info = ydl.extract_info(self.url, download=False)
            if not info or info.get("_type") == "playlist":
                return None

            path: str = ydl.prepare_filename(info)  # type: ignore[no-untyped-call]

            merge_fmt = self.ydl_opts.get("merge_output_format")
            if merge_fmt:
                base, _ = os.path.splitext(path)
                path = f"{base}.{merge_fmt}"

            is_audio = any(
                pp.get("key") == "FFmpegExtractAudio"
                for pp in self.ydl_opts.get("postprocessors", [])
            )
            if is_audio:
                base, _ = os.path.splitext(path)
                path = f"{base}.mp3"

            # Return the path even if the file is missing — the caller
            # (the CLI) will check os.path.isfile and report accordingly.
            return path
        except Exception:
            return None

    @staticmethod
    def _resolve_outtmpl(ydl_opts: dict) -> str:
        """Extract the output template string from *ydl_opts*.

        yt-dlp ≥2026.07.04 converts the ``outtmpl`` string into a dict
        with ``default`` and optional ``chapter`` keys during processing.
        This helper returns the ``default`` entry when given a dict, or
        the raw string when given a string.
        """
        raw = ydl_opts.get("outtmpl", "")
        if isinstance(raw, dict):
            return str(raw.get("default", ""))
        return str(raw) if raw else ""

    def _resolve_output_path(self) -> str:
        is_audio = any(
            pp.get("key") == "FFmpegExtractAudio"
            for pp in self.ydl_opts.get("postprocessors", [])
        )

        # ── Direct path from the "finished" hook (yt-dlp ≤2025) ──
        # yt-dlp ≥2026.07.04 no longer sends a "finished" status in the
        # progress hook, so _original_filename may remain unset.
        if self._original_filename:
            path = self._original_filename
            if is_audio:
                path = os.path.splitext(path)[0] + ".mp3"
            if os.path.exists(path):
                return path

        # ── Fallback: scan the output directory for the newest valid
        # media file that is not a temp / part file.  This works with
        # both yt-dlp ≤2025 (where fragments get deleted after merge)
        # and yt-dlp ≥2026 (where the "finished" hook is absent).
        outtmpl = self._resolve_outtmpl(self.ydl_opts)
        outdir = os.path.dirname(outtmpl) if outtmpl else ""
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

        # ── Last resort: return the original path even if vanished ─
        if self._original_filename:
            path = self._original_filename
            if is_audio:
                path = os.path.splitext(path)[0] + ".mp3"
            if os.path.exists(path):
                return path

        return ""
