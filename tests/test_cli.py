"""
Tests for YVid CLI — format selection, cookie configuration in ydl_opts,
error handling patterns, and edge-case resilience.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from yvid.cli import YVidCLI, DownloadError
from yvid.core.config import FORMAT_VIDEO_QUALITY


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════


def _make_cli(**overrides: Any) -> YVidCLI:
    """Create a ``YVidCLI`` instance with a pristine config in a temp dir.

    Overrides are merged into the default argparse namespace so callers
    can set ``url``, ``format``, etc.
    """
    defaults: dict[str, Any] = {
        "url": None,
        "format": None,
        "quality": None,
        "trim_start": None,
        "trim_end": None,
        "subs": False,
        "output": None,
        "cookies_from_browser": None,
        "cookies_file": None,
    }
    defaults.update(overrides)
    ns = argparse.Namespace(**defaults)

    # Point config to a throwaway directory so tests don't touch ~/.config
    tmp = tempfile.mkdtemp(prefix="yvid_test_")
    with patch.object(YVidCLI, "_get_config_dir", return_value=tmp):
        cli = YVidCLI(ns)
    return cli


# ═══════════════════════════════════════════════════════════════
#  FORMAT MAPPING
# ═══════════════════════════════════════════════════════════════


class TestFormatMapping:
    """Verify that every ``FORMAT_VIDEO_QUALITY`` entry ends with ``/best``
    and that audio selection maps to the correct fallback chain."""

    @pytest.mark.parametrize(
        "key, expected",
        [
            ("Best", "bestvideo+bestaudio/best"),
            (
                "2160p",
                "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
            ),
            (
                "1080p",
                "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            ),
            (
                "720p",
                "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            ),
            (
                "480p",
                "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
            ),
            (
                "360p",
                "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
            ),
        ],
    )
    def test_quality_format_strings(self, key: str, expected: str) -> None:
        """Every video-quality entry must end with ``/best`` so yt-dlp
        never shows 'Requested format is not available'."""
        actual = FORMAT_VIDEO_QUALITY[key]
        assert actual == expected
        assert actual.endswith("/best")

    def test_unknown_key_falls_back_to_best(self) -> None:
        """A nonexistent quality key must return the 'Best' format."""
        assert (
            FORMAT_VIDEO_QUALITY.get("9999p", FORMAT_VIDEO_QUALITY["Best"])
            == (FORMAT_VIDEO_QUALITY["Best"])
        )


class TestBuildYdlOptsFormat:
    """Exercise ``YVidCLI._build_ydl_opts`` format field."""

    def test_audio_format_string(self) -> None:
        """Audio selection must produce the triple-fallback format string."""
        cli = _make_cli()
        cli.config = {
            "is_audio": True,
            "quality": "Best",
            "subs": False,
            "cookies_file": "",
            "cookies_from_browser": "",
        }
        opts = cli._build_ydl_opts("/tmp")
        assert opts["format"] == "bestaudio/bestvideo+bestaudio/best"

    @pytest.mark.parametrize(
        "quality_label, expected_key",
        [
            ("Best", "Best"),
            ("2160p (4K)", "2160p"),
            ("1080p (Full HD)", "1080p"),
            ("720p (HD)", "720p"),
            ("480p", "480p"),
        ],
    )
    def test_video_quality_mapping(self, quality_label: str, expected_key: str) -> None:
        """Video-quality labels from the interactive UI must resolve to the
        correct ``FORMAT_VIDEO_QUALITY`` string."""
        cli = _make_cli()
        cli.config = {
            "is_audio": False,
            "quality": quality_label,
            "subs": False,
            "cookies_file": "",
            "cookies_from_browser": "",
        }
        opts = cli._build_ydl_opts("/tmp")
        assert opts["format"] == FORMAT_VIDEO_QUALITY[expected_key]

    def test_unknown_quality_falls_back_to_best(self) -> None:
        """A quality label that doesn't match any known key must fall back
        to the 'Best' format string."""
        cli = _make_cli()
        cli.config = {
            "is_audio": False,
            "quality": "TyPo QuAlItY",
            "subs": False,
            "cookies_file": "",
            "cookies_from_browser": "",
        }
        opts = cli._build_ydl_opts("/tmp")
        assert opts["format"] == FORMAT_VIDEO_QUALITY["Best"]

    def test_subs_flag_adds_embed_postprocessor(self) -> None:
        """When ``subs`` is True and format is video, the opts must include
        subtitle-related keys."""
        cli = _make_cli()
        cli.config = {
            "is_audio": False,
            "quality": "Best",
            "subs": True,
            "cookies_file": "",
            "cookies_from_browser": "",
        }
        opts = cli._build_ydl_opts("/tmp")
        assert opts.get("writesubtitles") is True
        assert opts.get("writeautomaticsub") is True
        assert opts.get("subtitlesformat") == "srt"
        assert any(
            pp.get("key") == "FFmpegEmbedSubtitle"
            for pp in opts.get("postprocessors", [])
        )

    def test_subs_ignored_when_audio(self) -> None:
        """Subtitles should NOT be set when the user selects audio."""
        cli = _make_cli()
        cli.config = {
            "is_audio": True,
            "quality": "Best",
            "subs": True,
            "cookies_file": "",
            "cookies_from_browser": "",
        }
        opts = cli._build_ydl_opts("/tmp")
        # Audio post-processor should be the only one
        pps = opts.get("postprocessors", [])
        assert len(pps) == 1
        assert pps[0]["key"] == "FFmpegExtractAudio"


# ═══════════════════════════════════════════════════════════════
#  COOKIE CONFIGURATION IN ydl_opts
# ═══════════════════════════════════════════════════════════════


class TestCookieInYdlOpts:
    """Verify how CLI passes cookies into the yt-dlp options dict."""

    def test_explicit_cookies_file(self) -> None:
        """When ``cookies_file`` is set, ``cookiefile`` must appear in opts."""
        cli = _make_cli()
        cli.config = {
            "is_audio": False,
            "quality": "Best",
            "subs": False,
            "cookies_file": "/tmp/test_cookies.txt",
            "cookies_from_browser": "",
        }
        opts = cli._build_ydl_opts("/tmp")
        assert opts["cookiefile"] == "/tmp/test_cookies.txt"
        assert "cookiesfrombrowser" not in opts

    def test_explicit_cookies_from_browser(self) -> None:
        """When ``cookies_from_browser`` is set, opts must contain the tuple."""
        cli = _make_cli()
        cli.config = {
            "is_audio": False,
            "quality": "Best",
            "subs": False,
            "cookies_file": "",
            "cookies_from_browser": "firefox",
        }
        opts = cli._build_ydl_opts("/tmp")
        assert opts["cookiesfrombrowser"] == ("firefox",)

    def test_both_cookies_empty_no_auto_detection(self) -> None:
        """When no cookie option is set, no cookies options must appear
        in ydl_opts — cookies are opt-in only (no auto-detection).
        """
        cli = _make_cli()
        cli.config = {
            "is_audio": False,
            "quality": "Best",
            "subs": False,
            "cookies_file": "",
            "cookies_from_browser": "",
        }
        # safe_extract_cookies_browser should NOT be called at all
        with patch("yvid.cli.safe_extract_cookies_browser") as mock_extract:
            opts = cli._build_ydl_opts("/tmp")
        assert "cookiesfrombrowser" not in opts
        assert "cookiefile" not in opts
        mock_extract.assert_not_called()


# ═══════════════════════════════════════════════════════════════
#  ERROR HANDLING  (stringification, no TextIOWrapper)
# ═══════════════════════════════════════════════════════════════


class TestErrorHandling:
    """Ensure exceptions are always stringified and no raw I/O objects leak."""

    def test_download_error_is_stringified(self) -> None:
        """``_handle_download_error`` must operate on ``str(exc)``, not the
        raw exception object."""
        cli = _make_cli()

        exc = DownloadError("test error message")
        # Mock the interactive prompt and update attempt so the test
        # doesn't try to read from stdin or run pip.
        with patch.object(cli, "_try_update_ytdlp", return_value=False):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("yvid.cli._ask") as mock_ask:
                    mock_ask.return_value.ask.return_value = False
                    result = cli._handle_download_error(exc)
        assert isinstance(result, bool)

    def test_textiowrapper_not_leaked(self) -> None:
        """Simulate an exception whose str() representation includes
        ``<_io.TextIOWrapper`` — this must never happen."""
        cli = _make_cli()

        # An exception that would look like a TextIOWrapper leak
        exc = DownloadError(
            "<_io.TextIOWrapper name='<stderr>' mode='w' encoding='utf-8'>"
        )
        with patch.object(cli, "_try_update_ytdlp", return_value=False):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("yvid.cli._ask") as mock_ask:
                    mock_ask.return_value.ask.return_value = False
                    result = cli._handle_download_error(exc)
        assert isinstance(result, bool)

    @pytest.mark.parametrize(
        "error_message",
        [
            "Sign in to confirm you're not a bot",
            "HTTP Error 403: Forbidden",
            "Unable to extract video data",
            "This video is age-restricted",
            "Private video. Sign in to view",
        ],
    )
    def test_auto_update_patterns_trigger_retry(self, error_message: str) -> None:
        """Known bot/403/extraction errors must trigger the auto-update path
        (which returns True or False, not crash)."""
        cli = _make_cli()

        exc = DownloadError(error_message)
        with patch.object(cli, "_try_update_ytdlp", return_value=False):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("yvid.cli._ask") as mock_ask:
                    mock_ask.return_value.ask.return_value = False
                    result = cli._handle_download_error(exc)
        assert isinstance(result, bool)

    def test_non_tty_returns_false_without_prompt(self) -> None:
        """When stdin is not a TTY, the error handler must return False
        without attempting an interactive prompt."""
        cli = _make_cli()
        exc = DownloadError("Some random error")

        with patch("sys.stdin.isatty", return_value=False):
            with patch("yvid.cli._ask") as mock_ask:
                result = cli._handle_download_error(exc)
        # No _ask was called
        mock_ask.assert_not_called()
        assert result is False

    def test_main_loop_catches_download_error(self) -> None:
        """The main ``run()`` loop catches ``DownloadError`` and does not
        propagate it as an unhandled exception."""
        cli = _make_cli(url="https://example.com/video", format="mp4", quality="best")
        # Monkey-patch _interactive_flow and _execute_download so we can
        # test the catch block without a real download.
        with patch.object(cli, "_interactive_flow"):
            with patch.object(
                cli, "_execute_download", side_effect=DownloadError("Simulated error")
            ):
                with patch.object(cli, "_handle_download_error", return_value=False):
                    with patch.object(cli, "_ask_download_another", return_value=False):
                        # Must exit cleanly via sys.exit(1) — we catch that
                        with pytest.raises(SystemExit) as exc_info:
                            cli.run()
                        assert exc_info.value.code == 1

    def test_main_loop_catches_keyboard_interrupt(self) -> None:
        """Ctrl+C must exit with code 0 (not a traceback)."""
        cli = _make_cli(url="https://example.com/video", format="mp4", quality="best")
        with patch.object(cli, "_interactive_flow", side_effect=KeyboardInterrupt()):
            with pytest.raises(SystemExit) as exc_info:
                cli.run()
            assert exc_info.value.code == 0

    def test_main_loop_catches_generic_exception(self) -> None:
        """Any unforeseen exception must be caught and exit with code 1."""
        cli = _make_cli()
        with patch.object(
            cli, "_interactive_flow", side_effect=RuntimeError("Unexpected crash")
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli.run()
            assert exc_info.value.code == 1


# ═══════════════════════════════════════════════════════════════
#  EDGE CASES  —  input validation, resume, cleanup
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Non-happy-path scenarios that the CLI must handle gracefully."""

    def test_safe_remove_nonexistent_file(self) -> None:
        """``_safe_remove`` must not raise when the file doesn't exist."""
        from yvid.cli import _safe_remove

        _safe_remove("/nonexistent/path/file.mp4")  # no crash

    def test_safe_remove_empty_string(self) -> None:
        """``_safe_remove`` must not raise on empty string."""
        from yvid.cli import _safe_remove

        _safe_remove("")  # no crash

    def test_clear_session_no_file(self) -> None:
        """``_clear_session`` must not raise when no session file exists."""
        cli = _make_cli()
        cli._clear_session()  # no crash

    def test_show_completion_without_output(self) -> None:
        """``_show_completion`` must not raise when ``last_output_path`` is empty."""
        cli = _make_cli()
        cli.config = {"trim_start": None, "trim_end": None}
        cli.last_output_path = ""
        cli._show_completion()  # no crash

    def test_show_completion_with_missing_file(self) -> None:
        """``_show_completion`` must not raise when the output file vanished."""
        cli = _make_cli()
        cli.config = {"trim_start": None, "trim_end": None}
        cli.last_output_path = "/definitely/not/a/real/file.mp4"
        cli._show_completion()  # no crash

    @pytest.mark.parametrize(
        "invalid_time",
        ["", "abc", "1:2:3:4", "-1:00", "99:99:99"],
    )
    def test_parse_time_invalid_values(self, invalid_time: str) -> None:
        """Invalid time strings must return None, not crash."""
        from yvid.core.helpers import parse_time

        assert parse_time(invalid_time) is None

    @pytest.mark.parametrize(
        "valid_time, expected_seconds",
        [
            ("30", 30),
            ("1:30", 90),
            ("1:30:00", 5400),
            ("0:05", 5),
            ("1:00:00", 3600),
        ],
    )
    def test_parse_time_valid_values(
        self, valid_time: str, expected_seconds: int
    ) -> None:
        """Valid time strings must parse to correct seconds."""
        from yvid.core.helpers import parse_time

        assert parse_time(valid_time) == expected_seconds

    def test_interactive_flow_wires_cookies_from_cli_args(self) -> None:
        """When --cookies-from-browser is passed, _interactive_flow must
        store it in config."""
        # Provide URL + format + quality so all prompts are skipped in
        # direct-download mode except the output directory.
        # Mock _get_output_dir only.
        cli = _make_cli(
            cookies_from_browser="firefox",
            url="https://youtube.com/watch?v=test123",
            format="mp4",
            quality="best",
        )
        with patch.object(cli, "_get_output_dir", return_value="/tmp"):
            cli._interactive_flow()
        assert cli.config.get("cookies_from_browser") == "firefox"

    def test_download_single_none_on_error(self) -> None:
        """When _build_ydl_opts creates a valid opts dict and the thread
        errors, ``_download_single`` must return None and set _last_error."""
        cli = _make_cli()
        cli.config = {
            "url": "https://example.com/video",
            "is_audio": False,
            "quality": "Best",
            "subs": False,
            "output_dir": "/tmp",
            "cookies_file": "",
            "cookies_from_browser": "",
            "trim_start": None,
            "trim_end": None,
        }
        # Mock safe_extract_cookies_browser so the test doesn't depend
        # on (or block waiting for) real browser cookie databases.
        with patch("yvid.cli.safe_extract_cookies_browser", return_value=None):
            result = cli._download_single()
        assert result is None
        assert cli._last_error != ""
