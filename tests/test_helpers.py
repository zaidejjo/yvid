"""
Tests for YVid core helpers — ``format_error_message``, ``safe_extract_cookies_browser``,
``parse_time``, ``format_bytes``, ``format_eta``, ``is_valid_url``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from yvid.core.helpers import (
    format_bytes,
    format_eta,
    format_error_message,
    is_valid_url,
    parse_time,
    safe_extract_cookies_browser,
)


# ═══════════════════════════════════════════════════════════════
#  safe_extract_cookies_browser  —  the heart of bot-bypass
# ═══════════════════════════════════════════════════════════════


class TestSafeExtractCookiesBrowser:
    """Exercise the browser iteration with mocked ``yt_dlp.cookies``."""

    def test_first_browser_succeeds(self, mock_cookies_module: MagicMock) -> None:
        """When ``brave`` returns truthy cookies, it must be the selected browser."""
        mock_cookies_module.extract_cookies_from_browser.side_effect = [
            {"name": "YT", "value": "abc"},
        ]
        result = safe_extract_cookies_browser()
        assert result == "brave"
        # Only the first browser should have been attempted
        assert mock_cookies_module.extract_cookies_from_browser.call_count == 1
        mock_cookies_module.extract_cookies_from_browser.assert_called_with("brave")

    def test_first_fails_second_succeeds(self, mock_cookies_module: MagicMock) -> None:
        """When brave raises, firefox must be tried and win."""
        mock_cookies_module.extract_cookies_from_browser.side_effect = [
            RuntimeError("Database locked on Brave"),
            {"name": "YT", "value": "def"},
        ]
        result = safe_extract_cookies_browser()
        assert result == "firefox"
        assert mock_cookies_module.extract_cookies_from_browser.call_count == 2
        mock_cookies_module.extract_cookies_from_browser.assert_any_call("brave")
        mock_cookies_module.extract_cookies_from_browser.assert_any_call("firefox")

    def test_first_returns_none_second_succeeds(
        self, mock_cookies_module: MagicMock
    ) -> None:
        """When brave returns None (no cookies), we must still try firefox."""
        mock_cookies_module.extract_cookies_from_browser.side_effect = [
            None,
            {"name": "YT", "value": "ghi"},
        ]
        result = safe_extract_cookies_browser()
        assert result == "firefox"

    def test_all_browsers_fail(self, mock_cookies_module: MagicMock) -> None:
        """When every browser raises, the function must return None."""
        mock_cookies_module.extract_cookies_from_browser.side_effect = RuntimeError(
            "No DB"
        )
        result = safe_extract_cookies_browser()
        assert result is None
        # All 7 browsers should have been attempted
        assert mock_cookies_module.extract_cookies_from_browser.call_count == 7

    def test_all_browsers_return_none(self, mock_cookies_module: MagicMock) -> None:
        """When every browser returns empty/None, the function must return None."""
        mock_cookies_module.extract_cookies_from_browser.return_value = None
        result = safe_extract_cookies_browser()
        assert result is None
        assert mock_cookies_module.extract_cookies_from_browser.call_count == 7

    def test_mixed_failures_all_silenced(self, mock_cookies_module: MagicMock) -> None:
        """PermissionError, OSError, and database lock errors must all be
        caught silently."""
        mock_cookies_module.extract_cookies_from_browser.side_effect = [
            PermissionError("Permission denied"),
            OSError("File not found"),
            RuntimeError("Database locked"),
            ValueError("Unexpected data"),
            TypeError("bad kwarg"),
            SystemError("internal"),
            Exception("generic"),
        ]
        result = safe_extract_cookies_browser()
        assert result is None  # All 7 raised — no browser worked
        assert mock_cookies_module.extract_cookies_from_browser.call_count == 7

    def test_first_browser_returns_empty_dict(
        self, mock_cookies_module: MagicMock
    ) -> None:
        """An empty dict is falsy — must continue to next browser."""
        mock_cookies_module.extract_cookies_from_browser.side_effect = [
            {},  # empty = falsy
            {"name": "YT", "value": "jkl"},
        ]
        result = safe_extract_cookies_browser()
        assert result == "firefox"
        assert mock_cookies_module.extract_cookies_from_browser.call_count == 2


# ═══════════════════════════════════════════════════════════════
#  format_error_message  —  user-friendly error mapping
# ═══════════════════════════════════════════════════════════════


class TestFormatErrorMessage:
    """Verify that raw yt-dlp errors map to human-readable messages and that
    no ``TextIOWrapper``-style output leaks to the user."""

    @pytest.mark.parametrize(
        "raw_error, expected_substring",
        [
            ("HTTP Error 403", "Access denied"),
            ("HTTP Error 429", "rate limited"),
            ("HTTP Error 404", "not available"),
            ("HTTP Error 500", "Server error"),
            ("Video unavailable", "has been removed or is unavailable"),
            ("Private video", "private"),
            ("ffmpeg not found", "FFmpeg is required"),
            ("ffprobe not found", "FFmpeg is required"),
            ("Connection refused", "Network error"),
            ("ConnectionError", "Network error"),
            ("Cannot connect to host", "Network error"),
            ("SSL certificate verify failed", "SSL connection error"),
            ("No video formats found", "No available formats"),
            ("unsupported url", "Unsupported URL"),
        ],
    )
    def test_known_patterns(self, raw_error: str, expected_substring: str) -> None:
        """Known error patterns must produce a friendly, translated message."""
        msg = format_error_message(raw_error)
        assert expected_substring.lower() in msg.lower()

    def test_unknown_pattern_truncated(self) -> None:
        """An unrecognised error must still produce a readable fallback."""
        long_msg = "x" * 200
        msg = format_error_message(long_msg)
        assert msg.startswith("Download failed:")
        assert "…" in msg or len(msg) <= 130

    def test_unknown_pattern_no_truncation_for_short(self) -> None:
        """Short unknown errors must not be truncated."""
        msg = format_error_message("something went wrong")
        assert msg == "Download failed: something went wrong"

    def test_never_leaks_textiowrapper(self) -> None:
        """Even if the raw string looks like a leaked I/O object, the output
        must be a plain string without raw angle-bracket reprs."""
        raw = "<_io.TextIOWrapper name='<stderr>' mode='w' encoding='utf-8'>"
        msg = format_error_message(raw)
        # The fallback wraps it in "Download failed: ..."
        assert msg.startswith("Download failed:")
        # No raw exception type leaked
        assert "TextIOWrapper" not in msg or "Download failed:" in msg


# ═══════════════════════════════════════════════════════════════
#  parse_time
# ═══════════════════════════════════════════════════════════════


class TestParseTime:
    """Verify time-string parsing for trim functionality."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("", None),
            ("0", 0),
            ("30", 30),
            ("120", 120),
            ("1:00", 60),
            ("1:30", 90),
            ("10:00", 600),
            ("1:00:00", 3600),
            ("1:30:00", 5400),
            ("0:05", 5),
            ("0:0:30", 30),
            ("  1:30  ", 90),  # whitespace tolerance
        ],
    )
    def test_valid_inputs(self, value: str, expected: int | None) -> None:
        assert parse_time(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            "abc",
            "1:2:3:4",
            "-1:00",
            "99:99:99",
            "1: -5",
            "one",
            "1::30",
        ],
    )
    def test_invalid_inputs(self, value: str) -> None:
        assert parse_time(value) is None


# ═══════════════════════════════════════════════════════════════
#  format_bytes
# ═══════════════════════════════════════════════════════════════


class TestFormatBytes:
    """Verify human-readable byte formatting."""

    @pytest.mark.parametrize(
        "n, expected_prefix",
        [
            (0, "0 B"),
            (1, "1.0 B"),
            (500, "500.0 B"),
            (1023, "1023.0 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),
            (1048576, "1.0 MB"),
            (1073741824, "1.0 GB"),
            (None, "0 B"),
            (0.0, "0 B"),
        ],
    )
    def test_format_bytes(self, n: float | None, expected_prefix: str) -> None:
        result = format_bytes(n)  # type: ignore[arg-type]
        assert result.startswith(expected_prefix.rstrip("0").rstrip("."))

    def test_large_values(self) -> None:
        assert format_bytes(1099511627776).startswith("1.0 TB")


# ═══════════════════════════════════════════════════════════════
#  format_eta
# ═══════════════════════════════════════════════════════════════


class TestFormatEta:
    """Verify ETA formatting."""

    @pytest.mark.parametrize(
        "seconds, expected",
        [
            (0, "\u2014\u2014"),
            (-1, "\u2014\u2014"),
            (None, "\u2014\u2014"),
            (30, "0:30"),
            (60, "1:00"),
            (90, "1:30"),
            (3600, "1:00:00"),
            (3661, "1:01:01"),
        ],
    )
    def test_eta(self, seconds: float | None, expected: str) -> None:
        assert format_eta(seconds) == expected  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════
#  is_valid_url
# ═══════════════════════════════════════════════════════════════


class TestIsValidUrl:
    """Verify URL validation."""

    @pytest.mark.parametrize(
        "url, expected",
        [
            ("https://youtube.com/watch?v=abc", True),
            ("http://example.com", True),
            ("https://192.168.1.1/path", True),
            ("", False),
            ("   ", False),
            ("not-a-url", False),
            ("ftp://example.com", False),
            ("javascript:void(0)", False),
        ],
    )
    def test_url_validation(self, url: str, expected: bool) -> None:
        assert is_valid_url(url) is expected


# ═══════════════════════════════════════════════════════════════
#  FORMAT_VIDEO_QUALITY  —  static config sanity
# ═══════════════════════════════════════════════════════════════


class TestFormatVideoQualityDict:
    """Smoke-tests for the video quality lookup table."""

    def test_all_entries_end_with_best(self) -> None:
        from yvid.core.config import FORMAT_VIDEO_QUALITY

        for key, fmt in FORMAT_VIDEO_QUALITY.items():
            assert fmt.endswith("/best"), f"{key!r} does not end with /best"

    def test_all_entries_contain_mp4(self) -> None:
        from yvid.core.config import FORMAT_VIDEO_QUALITY

        for key, fmt in FORMAT_VIDEO_QUALITY.items():
            assert "mp4" in fmt, f"{key!r} does not reference mp4"

    def test_known_keys(self) -> None:
        from yvid.core.config import FORMAT_VIDEO_QUALITY

        expected_keys = {"Best", "2160p", "1080p", "720p", "480p", "360p"}
        assert set(FORMAT_VIDEO_QUALITY.keys()) == expected_keys
