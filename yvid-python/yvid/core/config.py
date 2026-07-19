"""
Shared YVid configuration — constants, format maps, error patterns.
"""

from __future__ import annotations

from pathlib import Path

# ── Application metadata ────────────────────────────────────

APP_NAME = "YVid"
CLI_APP_NAME = "YVid-CLI"
VERSION = "1.0.0"
DEFAULT_OUTPUT_DIR = str(Path.home() / "Videos" / "YVid")

# ── Video quality → yt-dlp format string ────────────────────

FORMAT_VIDEO_QUALITY: dict[str, str] = {
    "Best": "bestvideo+bestaudio/best",
    "2160p": ("bestvideo[height<=2160]+bestaudio/best[height<=2160]/best"),
    "1080p": ("bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"),
    "720p": ("bestvideo[height<=720]+bestaudio/best[height<=720]/best"),
    "480p": ("bestvideo[height<=480]+bestaudio/best[height<=480]/best"),
    "360p": ("bestvideo[height<=360]+bestaudio/best[height<=360]/best"),
}

# ── Error patterns ──────────────────────────────────────────

ERROR_PATTERNS: list[tuple[str, str]] = [
    (r"HTTP Error 403", "Access denied. The video may be private or age-restricted."),
    (r"HTTP Error 429", "Request rate limited. Wait a moment and retry."),
    (r"HTTP Error 4\d\d", "Video not available (server returned {code})."),
    (r"HTTP Error 5\d\d", "Server error. The platform may be experiencing issues."),
    (r"Video unavailable", "This video has been removed or is unavailable."),
    (r"Private video", "This video is private. Sign-in is required."),
    (
        r"ffmpeg not found|ffprobe not found",
        "FFmpeg is required. Install FFmpeg and try again.",
    ),
    (
        r"Connection refused|ConnectionError|Cannot connect",
        "Network error. Check your internet connection.",
    ),
    (r"SSL", "SSL connection error. Check your network or date settings."),
    (
        r"Requested format is not available",
        "Requested format is not available for this video. Try a different quality or format.",
    ),
    (r"No video formats found", "No available formats found for this video."),
    (r"unsupported url", "Unsupported URL. Please enter a valid video URL."),
]
