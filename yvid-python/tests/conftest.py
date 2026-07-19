"""
Shared pytest fixtures for YVid tests.

Provides helpers to mock ``yt_dlp.cookies.extract_cookies_from_browser``
so we can exercise the ``safe_extract_cookies_browser`` function without
real browser databases.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_cookies_module() -> Generator[Mock, None, None]:
    """Mock ``yt_dlp.cookies`` so ``extract_cookies_from_browser`` is
    a controllable MagicMock.

    Usage in a test::

        def test_something(mock_cookies_module):
            mock_cookies_module.extract_cookies_from_browser.return_value = ...
            mock_cookies_module.extract_cookies_from_browser.side_effect = ...
    """
    with patch("yt_dlp.cookies") as mock:
        yield mock


# ── Convenience: pre-configured cookie mocks ──────────────────


@pytest.fixture
def cookie_always_fails(mock_cookies_module: Mock) -> Mock:
    """Make every browser raise an exception."""
    mock_cookies_module.extract_cookies_from_browser.side_effect = RuntimeError(
        "DB locked"
    )
    return mock_cookies_module


@pytest.fixture
def cookie_first_browser_succeeds(mock_cookies_module: Mock) -> Mock:
    """Return truthy cookies from the first browser attempted (brave)."""
    mock_cookies_module.extract_cookies_from_browser.side_effect = [
        {"name": "test_cookie", "value": "1"},  # brave succeeds
    ]
    return mock_cookies_module


@pytest.fixture
def cookie_second_browser_succeeds(mock_cookies_module: Mock) -> Mock:
    """First browser raises; second (firefox) returns cookies."""
    mock_cookies_module.extract_cookies_from_browser.side_effect = [
        RuntimeError("DB locked on brave"),
        {"name": "test_cookie", "value": "1"},  # firefox succeeds
    ]
    return mock_cookies_module


@pytest.fixture
def cookie_all_fail(mock_cookies_module: Mock) -> Mock:
    """Every browser raises — full failure path."""
    mock_cookies_module.extract_cookies_from_browser.side_effect = RuntimeError(
        "No browser available"
    )
    return mock_cookies_module


# ── CLI monkeypatch helpers ───────────────────────────────────


@pytest.fixture
def minimal_cli_args() -> dict[str, Any]:
    """Return the minimum argparse Namespace kwargs needed by ``YVidCLI``."""
    return {
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
