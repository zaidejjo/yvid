"""
Shared helper functions for YVid — formatting, validation, error mapping.
"""

from __future__ import annotations

import os
import re

from .config import ERROR_PATTERNS


def format_bytes(n: float) -> str:
    """Human-readable byte count (e.g. 1.5 MB, 2.3 GB)."""
    if not n:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    n = float(n)
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    return f"{n:.1f} {units[i]}"


def format_eta(seconds: float) -> str:
    """Human-readable ETA string (e.g. 1:23, 1:02:30)."""
    if not seconds or seconds < 0:
        return "\u2014\u2014"
    s = int(seconds)
    if s < 60:
        return f"0:{s:02d}"
    if s < 3600:
        return f"{s // 60}:{s % 60:02d}"
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def is_valid_url(url: str) -> bool:
    """Return True if *url* looks like a valid HTTP(S) URL."""
    url = url.strip()
    if not url:
        return False
    return bool(re.match(r"^https?://[^\s/$.?#].[^\s]*$", url))


def format_error_message(error_str: str) -> str:
    """Map a raw yt-dlp error string to a user-friendly message.

    Uses the pattern list from :mod:`core.config`.  Falls back to a
    truncated version of the raw string when no pattern matches.
    """
    for pattern, message in ERROR_PATTERNS:
        match = re.search(pattern, error_str, re.IGNORECASE)
        if match:
            code = match.group(0) if match.lastgroup is None else ""
            return message.format(code=code)
    msg = error_str.strip()[:120]
    if len(error_str) > 120:
        msg += "\u2026"
    return f"Download failed: {msg}"


def parse_time(value: str) -> int | None:
    """Convert *HH:MM:SS*, *MM:SS* or *SS* to total seconds.

    Returns ``None`` when the value is empty or the format is invalid.
    """
    s = value.strip()
    if not s:
        return None
    parts = s.split(":")
    if len(parts) > 3:
        return None
    try:
        parts_int = [int(p) for p in parts]
    except ValueError:
        return None
    if any(p < 0 for p in parts_int):
        return None
    if len(parts_int) == 1:
        return parts_int[0]
    if len(parts_int) == 2:
        if parts_int[1] >= 60:
            return None
        return parts_int[0] * 60 + parts_int[1]
    if parts_int[1] >= 60 or parts_int[2] >= 60:
        return None
    return parts_int[0] * 3600 + parts_int[1] * 60 + parts_int[2]


def human_readable_eta(remaining_seconds: float) -> str:
    """Alias for :func:`format_eta` — matches yt-dlp output expectations."""
    return format_eta(remaining_seconds)


def _check_ffmpeg() -> bool:
    """Return True if ffmpeg is available on the system PATH."""
    from shutil import which

    return which("ffmpeg") is not None


# ── Browser cookie extraction ─────────────────────────────


def safe_extract_cookies_browser() -> str | None:
    """Try each popular browser in order; return the first that yields cookies.

    Silently skips browsers that are not installed, have locked databases,
    or raise any other exception.  Returns ``None`` when every browser
    failed, so the caller can fall back to ``("all",)``.
    """
    import yt_dlp.cookies

    browsers_to_try = (
        "brave",
        "firefox",
        "chrome",
        "chromium",
        "edge",
        "opera",
        "vivaldi",
    )
    for browser in browsers_to_try:
        try:
            cookies = yt_dlp.cookies.extract_cookies_from_browser(browser)
            if cookies:
                return browser
        except Exception:  # noqa: BLE001
            continue
    return None
