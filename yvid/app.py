#!/usr/bin/env python3
"""
YVid — Modern Desktop Video Downloader
Built with CustomTkinter + yt-dlp + FFmpeg

Shared core logic lives under ``core/``.
"""

# ═══════════════════════════════════════════════════════════
#  IMPORTS
# ═══════════════════════════════════════════════════════════

from __future__ import annotations

import collections.abc
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter.font as tkfont
import tkinter.ttk as ttk
from tkinter import filedialog, StringVar, BooleanVar

import customtkinter as ctk
import yt_dlp
from PIL import Image, ImageDraw, ImageTk

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
    safe_extract_cookies_browser,
)
from .core.download_thread import DownloadThread

# ═══════════════════════════════════════════════════════════
#  CONSTANTS  (GUI-specific only — shared values in core.config)
# ═══════════════════════════════════════════════════════════

WINDOW_WIDTH = 620
WINDOW_HEIGHT = 600
MIN_WIDTH = 580
MIN_HEIGHT = 520
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
ICON_SCALE = 5  # Draw at 5× resolution for crisp downscaled anti-aliasing

# Explicit background colors for Linux corner-blending (prevents jagged rendering)
BG_WINDOW = ("gray92", "gray14")  # Matches the blue-theme window background
BG_CARD = ("gray97", "gray20")  # Slightly lighter card for the settings panel

# ═══════════════════════════════════════════════════════════
#  SYSTEM FONT DETECTION  (Linux fc-match)
# ═══════════════════════════════════════════════════════════


def detect_system_font() -> str:
    """Query the OS for the default sans-serif font family.

    On Linux this uses ``fc-match`` (fontconfig).  On macOS / Windows
    well-known platform fonts are returned.  Falls back to ``sans-serif``
    which Tkinter resolves via Xft/fontconfig on most modern systems.
    """
    if sys.platform == "linux":
        try:
            out = subprocess.check_output(
                ["fc-match", "--format=%{family[0]}", "sans-serif"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
            ).strip()
            if out:
                return out.split(",")[0]
        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
        ):
            pass
        # Well-known Linux fallbacks with excellent antialiasing
        for candidate in ("Ubuntu", "Noto Sans", "DejaVu Sans", "Liberation Sans"):
            try:
                subprocess.run(
                    ["fc-match", candidate],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                return candidate
            except FileNotFoundError:
                continue

    if sys.platform == "darwin":
        return "Helvetica Neue"
    if sys.platform == "win32":
        return "Segoe UI"
    return "sans-serif"


# ═══════════════════════════════════════════════════════════
#  ICON GENERATION  (vector icons drawn with Pillow)
# ═══════════════════════════════════════════════════════════


def _draw_paste(
    draw: ImageDraw.ImageDraw, size: tuple[int, int], color: tuple[int, int, int]
) -> None:
    w, h = size
    m = max(w // 12, 2)
    # clipboard body
    draw.rounded_rectangle(
        [m, h // 4, w - m, h - m],
        radius=w // 10,
        fill=None,
        outline=color,
        width=max(1, w // 22),
    )
    # document lines
    ys = h // 3
    sp = max(h // 9, 2)
    lw = max(w // 32, 1)
    for i in range(3):
        y = ys + i * sp
        draw.line([(w // 3, y), (2 * w // 3, y)], fill=color, width=lw)
    # clip
    cw = max(w // 3, 4)
    cx = (w - cw) // 2
    draw.rectangle(
        [cx, 0, cx + cw, h // 4], fill=None, outline=color, width=max(1, w // 22)
    )


def _draw_folder(
    draw: ImageDraw.ImageDraw, size: tuple[int, int], color: tuple[int, int, int]
) -> None:
    w, h = size
    # folder body
    draw.rounded_rectangle(
        [2, h // 4, w - 2, h - 2],
        radius=w // 10,
        fill=None,
        outline=color,
        width=max(1, w // 22),
    )
    # tab
    draw.rectangle(
        [2, h // 4 - h // 8, w // 3, h // 4 + 2],
        fill=color,
        outline=color,
        width=max(1, w // 22),
    )


def _draw_chevron_down(
    draw: ImageDraw.ImageDraw, size: tuple[int, int], color: tuple[int, int, int]
) -> None:
    w, h = size
    m = w // 6
    lw = max(w // 12, 1)
    draw.line([(m, h // 3), (w // 2, 2 * h // 3)], fill=color, width=lw)
    draw.line([(w // 2, 2 * h // 3), (w - m, h // 3)], fill=color, width=lw)


def _draw_chevron_up(
    draw: ImageDraw.ImageDraw, size: tuple[int, int], color: tuple[int, int, int]
) -> None:
    w, h = size
    m = w // 6
    lw = max(w // 12, 1)
    draw.line([(m, 2 * h // 3), (w // 2, h // 3)], fill=color, width=lw)
    draw.line([(w // 2, h // 3), (w - m, 2 * h // 3)], fill=color, width=lw)


def _draw_download(
    draw: ImageDraw.ImageDraw, size: tuple[int, int], color: tuple[int, int, int]
) -> None:
    w, h = size
    cx = w // 2
    lw = max(w // 14, 1)
    # shaft
    draw.line([(cx, h // 6), (cx, 2 * h // 3)], fill=color, width=lw)
    # arrowhead
    draw.line([(cx, 2 * h // 3), (w // 4, h // 2)], fill=color, width=lw)
    draw.line([(cx, 2 * h // 3), (3 * w // 4, h // 2)], fill=color, width=lw)
    # tray
    ty = 5 * h // 6
    draw.line([(w // 4, ty), (3 * w // 4, ty)], fill=color, width=lw)


def _draw_play(
    draw: ImageDraw.ImageDraw, size: tuple[int, int], color: tuple[int, int, int]
) -> None:
    w, h = size
    draw.polygon(
        [(w // 3, h // 4), (3 * w // 4, h // 2), (w // 3, 3 * h // 4)],
        fill=color,
        outline=color,
    )


ICON_DEFS: dict[str, tuple[int, int, collections.abc.Callable]] = {
    "paste": (18, 18, _draw_paste),
    "folder": (18, 18, _draw_folder),
    "chevron_down": (12, 12, _draw_chevron_down),
    "chevron_up": (12, 12, _draw_chevron_up),
    "download": (20, 20, _draw_download),
    "play": (18, 18, _draw_play),
}


def generate_icons(assets_dir: str) -> None:
    os.makedirs(assets_dir, exist_ok=True)

    light_color = (70, 70, 75)
    dark_color = (195, 195, 200)

    for name, (disp_w, disp_h, draw_func) in ICON_DEFS.items():
        hi_w = disp_w * ICON_SCALE
        hi_h = disp_h * ICON_SCALE

        # -- light variant --
        img = Image.new("RGBA", (hi_w, hi_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw_func(draw, (hi_w, hi_h), light_color)
        img.resize((disp_w, disp_h), Image.LANCZOS).save(
            os.path.join(assets_dir, f"{name}_light.png")
        )

        # -- dark variant --
        img = Image.new("RGBA", (hi_w, hi_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw_func(draw, (hi_w, hi_h), dark_color)
        img.resize((disp_w, disp_h), Image.LANCZOS).save(
            os.path.join(assets_dir, f"{name}_dark.png")
        )


def load_icons(assets_dir: str) -> dict[str, ctk.CTkImage | None]:
    icons: dict[str, ctk.CTkImage | None] = {}
    for name, (disp_w, disp_h, _) in ICON_DEFS.items():
        light_path = os.path.join(assets_dir, f"{name}_light.png")
        dark_path = os.path.join(assets_dir, f"{name}_dark.png")
        try:
            li = (
                Image.open(light_path)
                if os.path.exists(light_path)
                else Image.new("RGBA", (1, 1))
            )
            di = Image.open(dark_path) if os.path.exists(dark_path) else li
            icons[name] = ctk.CTkImage(
                light_image=li, dark_image=di, size=(disp_w, disp_h)
            )
        except Exception:
            icons[name] = None
    return icons


# ═══════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════


class App(ctk.CTk):
    """YVid main window."""

    # ── lifecycle ───────────────────────────────────────

    def __init__(self) -> None:
        super().__init__()

        # theme — must be set before any widget creation
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # ── high-DPI support (Windows) ──
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                pass

        # ── detect system font (fc-match on Linux) ──
        self.font_family = detect_system_font()

        # ── high-quality font rendering ──
        try:
            default_font = tkfont.nametofont("TkDefaultFont")
            default_font.configure(family=self.font_family, size=13)
        except Exception:
            pass

        # ── prevent native Tk border bleed ──
        try:
            self.tk.call("tk", "scaling", 1.0)
        except Exception:
            pass

        # ── force themed dialog appearance (last-resort tkinter fallback) ──
        try:
            style = ttk.Style(self)
            for theme_candidate in ("clam", "alt"):
                if theme_candidate in style.theme_names():
                    style.theme_use(theme_candidate)
                    break
        except Exception:
            pass

        # window
        self.title(f"{APP_NAME}  \u2014  Video Downloader")
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.center_window(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # state
        self.download_in_progress = False
        self.last_output_path: str = ""
        self.progress_queue: queue.Queue = queue.Queue()
        self._download_thread: DownloadThread | None = None

        # tkinter variables
        self.quality_var = StringVar(value="Best")
        self.subs_var = BooleanVar(value=False)
        self.output_var = StringVar(value=DEFAULT_OUTPUT_DIR)

        # assets
        self.icons = self._setup_assets()

        # optional window icon  (assets/logo.png  or  .ico on Windows)
        self._load_window_icon()

        # build UI
        self._build_ui()
        self._settings_visible = True  # start expanded

        # start queue poller
        self.after(100, self._poll_queue)

    # ── window helpers ──────────────────────────────────

    def center_window(self, width: int, height: int, window=None) -> None:
        """Dynamically centre *window* (or ``self``) on the current screen.

        Retrieves the display resolution via ``winfo_screenwidth`` /
        ``winfo_screenheight``, computes the exact centre for the given
        dimensions, and applies ``geometry(...)`` in one call.
        """
        target = window if window is not None else self
        screen_width = target.winfo_screenwidth()
        screen_height = target.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        target.geometry(f"{width}x{height}+{x}+{y}")

    def _on_close(self) -> None:
        self.download_in_progress = False
        self.destroy()

    # ── assets ──────────────────────────────────────────

    def _setup_assets(self) -> dict[str, ctk.CTkImage | None]:
        try:
            generate_icons(ASSETS_DIR)
        except Exception:
            pass  # generation is best-effort
        return load_icons(ASSETS_DIR)

    def _load_window_icon(self) -> None:
        """Set the window icon from ``assets/logo.png`` or ``.ico``."""
        icon_path = os.path.join(ASSETS_DIR, "logo.png")
        ico_path = os.path.join(ASSETS_DIR, "logo.ico")
        try:
            if sys.platform == "win32" and os.path.isfile(ico_path):
                self.iconbitmap(ico_path)
            elif os.path.isfile(icon_path):
                img = Image.open(icon_path)
                img = img.resize((32, 32), Image.Resampling.LANCZOS)
                self.tk.call("wm", "iconphoto", self._w, ImageTk.PhotoImage(img))
        except Exception:
            pass  # non-critical

    # ── UI construction ─────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_url_section()
        self._build_settings_toggle()
        self._build_settings_panel()
        self._build_download_btn()
        self._build_progress_section()
        self._build_message_label()
        self._build_play_btn()

    def _font(self, size: int = 13, weight: str = "normal") -> ctk.CTkFont:
        """Shortcut for creating a font with the detected system family."""
        return ctk.CTkFont(family=self.font_family, size=size, weight=weight)

    # -- header ------------------------------------------

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=30, pady=(28, 20), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=APP_NAME,
            font=self._font(24, "bold"),
            bg_color="transparent",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Video Downloader",
            font=self._font(13),
            text_color=("gray50", "gray60"),
            bg_color="transparent",
        ).grid(row=1, column=0, sticky="w")

    # -- url input ---------------------------------------

    def _build_url_section(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, padx=30, pady=(0, 16), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Paste video URL here\u2026",
            height=44,
            corner_radius=10,
            border_width=1,
            border_color=("gray78", "gray35"),
            fg_color=("white", "gray17"),
            bg_color=BG_WINDOW,
            font=self._font(14),
        )
        self.url_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.url_entry.bind("<Return>", lambda _: self._start_download())

        paste_icon = self.icons.get("paste")
        self.paste_btn = ctk.CTkButton(
            frame,
            text="Paste",
            width=90,
            height=44,
            corner_radius=10,
            border_width=1,
            border_color=("#3B8ED0", "#1F6AA5"),
            fg_color=("#3B8ED0", "#1F6AA5"),
            bg_color=BG_WINDOW,
            font=self._font(13),
            image=paste_icon,
            compound="left",
            command=self._paste_url,
        )
        self.paste_btn.grid(row=0, column=1, sticky="e")

    # -- settings toggle header ---------------------------

    def _build_settings_toggle(self) -> None:
        self.settings_header = ctk.CTkFrame(self, fg_color="transparent", height=28)
        self.settings_header.grid(row=2, column=0, padx=30, pady=(0, 0), sticky="ew")
        self.settings_header.grid_columnconfigure(0, weight=1)
        self.settings_header.grid_propagate(False)

        sep = ctk.CTkFrame(
            self.settings_header,
            height=1,
            fg_color=("gray85", "gray35"),
            corner_radius=0,
            bg_color="transparent",
        )
        sep.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkLabel(
            self.settings_header,
            text="SETTINGS",
            font=self._font(12, "bold"),
            text_color=("gray50", "gray60"),
            bg_color="transparent",
        ).grid(row=0, column=0, padx=(0, 6))

        self.settings_chevron = ctk.CTkButton(
            self.settings_header,
            text="",
            width=28,
            height=28,
            corner_radius=6,
            fg_color="transparent",
            bg_color="transparent",
            border_width=0,
            hover_color=("gray85", "gray30"),
            image=self.icons.get("chevron_up"),
            command=self._toggle_settings,
        )
        self.settings_chevron.grid(row=0, column=1, sticky="e")

    # -- settings panel (collapsible) ---------------------

    def _build_settings_panel(self) -> None:
        sf = ctk.CTkFrame(
            self,
            corner_radius=14,
            fg_color=BG_CARD,
            border_width=0,
        )
        sf.grid(row=3, column=0, padx=30, pady=(10, 16), sticky="ew")
        sf.grid_columnconfigure(1, weight=1)
        self.settings_frame = sf

        # ---- row 0: Format ----
        ctk.CTkLabel(
            sf,
            text="Format",
            font=self._font(13),
            bg_color=BG_CARD,
        ).grid(row=0, column=0, padx=(18, 12), pady=(18, 8), sticky="w")

        self.format_seg = ctk.CTkSegmentedButton(
            sf,
            values=["Video MP4", "Audio MP3"],
            command=self._on_format_change,
            font=self._font(12),
            corner_radius=8,
            border_width=1,
            fg_color=("gray90", "gray22"),
            selected_color=("#2979FF", "#0A84FF"),
            selected_hover_color=("#1A6AE0", "#1A6AE0"),
            bg_color=BG_CARD,
        )
        self.format_seg.grid(row=0, column=1, padx=(0, 16), pady=(18, 8), sticky="ew")
        self.format_seg.set("Video MP4")

        # ---- row 1: Quality + Appearance ----
        inner1 = ctk.CTkFrame(sf, fg_color="transparent")
        inner1.grid(row=1, column=0, columnspan=2, padx=0, pady=0, sticky="ew")
        inner1.grid_columnconfigure(1, weight=1)
        inner1.grid_columnconfigure(3, weight=1)

        self.quality_label = ctk.CTkLabel(
            inner1,
            text="Quality",
            font=self._font(13),
            bg_color="transparent",
        )
        self.quality_label.grid(row=0, column=0, padx=(18, 8), pady=7, sticky="w")

        self.quality_menu = ctk.CTkOptionMenu(
            inner1,
            values=["Best", "2160p", "1080p", "720p", "480p", "360p"],
            font=self._font(12),
            corner_radius=8,
            dropdown_font=self._font(12),
            bg_color="transparent",
            variable=self.quality_var,
        )
        self.quality_menu.grid(row=0, column=1, padx=(0, 12), pady=7, sticky="ew")

        ctk.CTkLabel(
            inner1,
            text="Theme",
            font=self._font(13),
            bg_color="transparent",
        ).grid(row=0, column=2, padx=(4, 8), pady=7, sticky="w")

        self.theme_menu = ctk.CTkOptionMenu(
            inner1,
            values=["System", "Light", "Dark"],
            font=self._font(12),
            corner_radius=8,
            dropdown_font=self._font(12),
            bg_color="transparent",
            command=self._change_theme,
        )
        self.theme_menu.grid(row=0, column=3, padx=(0, 16), pady=7, sticky="ew")
        self.theme_menu.set("System")

        # ---- row 2: Subtitles ----
        self.subs_check = ctk.CTkCheckBox(
            sf,
            text="Download subtitles (if available)",
            font=self._font(13),
            variable=self.subs_var,
            corner_radius=4,
            border_width=1,
            border_color=("gray75", "gray38"),
            bg_color=BG_CARD,
            onvalue=True,
            offvalue=False,
        )
        self.subs_check.grid(
            row=2,
            column=0,
            columnspan=2,
            padx=(18, 16),
            pady=(6, 8),
            sticky="w",
        )

        # ---- row 3: Trim times ----
        self.trim_label = ctk.CTkLabel(
            sf,
            text="Trim",
            font=self._font(13),
            bg_color=BG_CARD,
        )
        self.trim_label.grid(row=3, column=0, padx=(18, 12), pady=(6, 6), sticky="w")

        self.trim_frame = ctk.CTkFrame(sf, fg_color="transparent")
        self.trim_frame.grid(row=3, column=1, padx=(0, 16), pady=(6, 6), sticky="ew")
        self.trim_frame.grid_columnconfigure(1, weight=1)
        self.trim_frame.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            self.trim_frame,
            text="Start",
            font=self._font(12),
            text_color=("gray50", "gray60"),
            bg_color="transparent",
        ).grid(row=0, column=0, padx=(0, 4), sticky="w")

        self.trim_start_entry = ctk.CTkEntry(
            self.trim_frame,
            placeholder_text="HH:MM:SS",
            width=100,
            height=34,
            corner_radius=8,
            border_width=1,
            border_color=("gray82", "gray35"),
            fg_color=("white", "gray17"),
            bg_color="transparent",
            font=self._font(12),
        )
        self.trim_start_entry.grid(
            row=0,
            column=1,
            padx=(0, 12),
            sticky="ew",
        )

        ctk.CTkLabel(
            self.trim_frame,
            text="End",
            font=self._font(12),
            text_color=("gray50", "gray60"),
            bg_color="transparent",
        ).grid(row=0, column=2, padx=(0, 4), sticky="w")

        self.trim_end_entry = ctk.CTkEntry(
            self.trim_frame,
            placeholder_text="HH:MM:SS",
            width=100,
            height=34,
            corner_radius=8,
            border_width=1,
            border_color=("gray82", "gray35"),
            fg_color=("white", "gray17"),
            bg_color="transparent",
            font=self._font(12),
        )
        self.trim_end_entry.grid(
            row=0,
            column=3,
            sticky="ew",
        )

        # ---- row 4: Output ----
        ctk.CTkLabel(
            sf,
            text="Output",
            font=self._font(13),
            bg_color=BG_CARD,
        ).grid(row=4, column=0, padx=(18, 12), pady=(4, 18), sticky="w")

        out_frame = ctk.CTkFrame(sf, fg_color="transparent")
        out_frame.grid(row=4, column=1, padx=(0, 16), pady=(4, 18), sticky="ew")
        out_frame.grid_columnconfigure(0, weight=1)

        self.output_entry = ctk.CTkEntry(
            out_frame,
            textvariable=self.output_var,
            font=self._font(12),
            height=34,
            corner_radius=8,
            border_width=1,
            border_color=("gray82", "gray35"),
            fg_color=("white", "gray17"),
            bg_color="transparent",
            state="readonly",
        )
        self.output_entry.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        self.browse_btn = ctk.CTkButton(
            out_frame,
            text="Browse",
            width=82,
            height=34,
            corner_radius=8,
            border_width=1,
            border_color=("gray82", "gray35"),
            fg_color=("gray97", "gray24"),
            hover_color=("gray88", "gray30"),
            bg_color="transparent",
            font=self._font(12),
            image=self.icons.get("folder"),
            compound="left",
            command=self._browse_output,
        )
        self.browse_btn.grid(row=0, column=1, sticky="e")

    # -- download button ---------------------------------

    def _build_download_btn(self) -> None:
        self.download_btn = ctk.CTkButton(
            self,
            text="Download",
            height=48,
            corner_radius=10,
            border_width=1,
            border_color=("#1A6AE0", "#0A6AE0"),
            fg_color=("#2979FF", "#0A84FF"),
            hover_color=("#1A6AE0", "#0073E0"),
            bg_color=BG_WINDOW,
            font=self._font(15, "bold"),
            image=self.icons.get("download"),
            compound="left",
            command=self._start_download,
        )
        self.download_btn.grid(row=4, column=0, padx=30, pady=(0, 20), sticky="ew")

    # -- progress section --------------------------------

    def _build_progress_section(self) -> None:
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            height=8,
            corner_radius=4,
            border_width=0,
            fg_color=("gray85", "gray28"),
            progress_color=("#2979FF", "#0A84FF"),
            bg_color="transparent",
            mode="determinate",
        )
        self.progress_bar.grid(row=0, column=0, padx=0, pady=(0, 8), sticky="ew")
        self.progress_bar.set(0)

        stats = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        stats.grid(row=1, column=0, sticky="ew")
        stats.grid_columnconfigure(1, weight=1)

        self.percent_label = ctk.CTkLabel(
            stats,
            text="",
            font=self._font(14, "bold"),
            width=62,
            anchor="w",
            bg_color="transparent",
        )
        self.percent_label.grid(row=0, column=0, sticky="w")

        self.speed_label = ctk.CTkLabel(
            stats,
            text="",
            font=self._font(13),
            anchor="center",
            bg_color="transparent",
        )
        self.speed_label.grid(row=0, column=1, sticky="ew")

        self.eta_label = ctk.CTkLabel(
            stats,
            text="",
            font=self._font(13),
            anchor="e",
            bg_color="transparent",
        )
        self.eta_label.grid(row=0, column=2, sticky="e")

        self.progress_frame.grid_remove()

    # -- message label -----------------------------------

    def _build_message_label(self) -> None:
        self.message_label = ctk.CTkLabel(
            self,
            text="",
            font=self._font(13),
            anchor="w",
            bg_color=BG_WINDOW,
        )
        self.message_label.grid(row=6, column=0, padx=30, pady=(4, 8), sticky="ew")

    # -- play button -------------------------------------

    def _build_play_btn(self) -> None:
        self.play_btn = ctk.CTkButton(
            self,
            text="Play with mpv",
            height=38,
            corner_radius=10,
            border_width=1,
            border_color=("gray82", "gray35"),
            fg_color=("gray88", "gray28"),
            hover_color=("gray78", "gray35"),
            text_color=("gray15", "gray85"),
            bg_color=BG_WINDOW,
            font=self._font(13),
            image=self.icons.get("play"),
            compound="left",
            command=self._play_video,
        )
        self.play_btn.grid_remove()

    # ── settings toggle ─────────────────────────────────

    def _toggle_settings(self) -> None:
        if self._settings_visible:
            self.settings_frame.grid_remove()
            self.settings_chevron.configure(image=self.icons.get("chevron_down"))
            self._settings_visible = False
        else:
            self.settings_frame.grid()
            self.settings_chevron.configure(image=self.icons.get("chevron_up"))
            self._settings_visible = True

    def _on_format_change(self, value: str) -> None:
        if value == "Audio MP3":
            self.quality_label.grid_remove()
            self.quality_menu.grid_remove()
            self.subs_check.grid_remove()
            self.trim_label.grid_remove()
            self.trim_frame.grid_remove()
        else:
            self.quality_label.grid()
            self.quality_menu.grid()
            self.subs_check.grid()
            self.trim_label.grid()
            self.trim_frame.grid()

    def _change_theme(self, mode: str) -> None:
        ctk.set_appearance_mode(mode)

    # ── actions ─────────────────────────────────────────

    def _paste_url(self) -> None:
        try:
            text = self.clipboard_get()
            if text:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, text)
        except Exception:
            pass

    def _browse_output(self) -> None:
        directory = self._pick_directory_native()
        if directory:
            self.output_var.set(directory)

    def _pick_directory_native(self) -> str:
        """Open the OS-native directory picker.

        Priority (Linux):
          1. ``zenity`` (GNOME) — subprocess
          2. ``kdialog`` (KDE)  — subprocess
          3. Tkinter ``filedialog.askdirectory`` with the ``clam`` theme
             (looks acceptable on modern Linux DEs).

        macOS / Windows → ``filedialog.askdirectory`` is already native.
        """
        initial = self.output_var.get() or DEFAULT_OUTPUT_DIR

        # -- Linux: try zenity / kdialog first ------------
        if sys.platform == "linux":
            try:
                out = subprocess.check_output(
                    [
                        "zenity",
                        "--file-selection",
                        "--directory",
                        "--title=Select Download Directory",
                        f"--filename={initial}/",
                    ],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=30,
                ).strip()
                if out:
                    return out
            except (
                FileNotFoundError,
                subprocess.TimeoutExpired,
                subprocess.CalledProcessError,
            ):
                pass

            try:
                out = subprocess.check_output(
                    ["kdialog", "--getexistingdirectory", initial],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=30,
                ).strip()
                if out:
                    return out
            except (
                FileNotFoundError,
                subprocess.TimeoutExpired,
                subprocess.CalledProcessError,
            ):
                pass

            # -- themed tkinter fallback ------------------
            try:
                style = ttk.Style(self)
                old_theme = style.theme_use()
                for name in ("clam", "alt"):
                    if name in style.theme_names():
                        style.theme_use(name)
                        break
                directory = filedialog.askdirectory(
                    title="Select Download Directory",
                    initialdir=initial,
                    parent=self,
                )
                style.theme_use(old_theme)
                return directory or ""
            except Exception:
                pass

        # -- macOS / Windows / last-resort ----------------
        return (
            filedialog.askdirectory(
                title="Select Download Directory",
                initialdir=initial,
                parent=self,
            )
            or ""
        )

    # ── download orchestration ──────────────────────────

    def _start_download(self) -> None:
        if self.download_in_progress:
            return

        url = self.url_entry.get().strip()
        if not is_valid_url(url):
            self._show_message("Please enter a valid video URL.", error=True)
            return

        is_audio = self.format_seg.get() == "Audio MP3"
        quality = self.quality_var.get()
        subs = self.subs_var.get()
        output_dir = self.output_var.get()

        ydl_opts = self._build_ydl_opts(is_audio, quality, subs, output_dir)

        # ── update UI ──
        self.download_in_progress = True
        self.download_btn.configure(text="Downloading\u2026", state="disabled")
        self._clear_message()
        self._reset_progress()
        self._show_progress_section()
        self.play_btn.grid_remove()

        # ── launch thread ──
        self.progress_queue = queue.Queue()
        self._download_thread = DownloadThread(url, ydl_opts, self.progress_queue)
        self._download_thread.start()

    # ── yt-dlp option builder ──────────────────────────

    @staticmethod
    def _build_ydl_opts(
        is_audio: bool,
        quality: str,
        subs: bool,
        output_dir: str,
    ) -> dict:
        os.makedirs(output_dir, exist_ok=True)

        ydl_opts: dict = {
            "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "no_playlist": True,
            "ignore_errors": False,
        }

        # ── Automatic cookies (frictionless bot bypass) ─────
        working_browser = safe_extract_cookies_browser()
        if working_browser:
            ydl_opts["cookiesfrombrowser"] = (working_browser,)
        else:
            ydl_opts["cookiesfrombrowser"] = ("all",)

        if is_audio:
            ydl_opts["format"] = "bestaudio/bestvideo+bestaudio/best"
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                },
            ]
        else:
            fmt = FORMAT_VIDEO_QUALITY.get(quality, FORMAT_VIDEO_QUALITY["Best"])
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
                ydl_opts["postprocessors"].append(
                    {
                        "key": "FFmpegEmbedSubtitle",
                    }
                )

        return ydl_opts

    # ── progress polling ────────────────────────────────

    def _poll_queue(self) -> None:
        try:
            if not self.download_in_progress:
                return

            try:
                while True:
                    d = self.progress_queue.get_nowait()

                    if d["status"] == "downloading":
                        self._update_progress(
                            d.get("percent", 0),
                            d.get("speed", 0),
                            d.get("eta", 0),
                        )

                    elif d["status"] == "post_processing":
                        self.progress_bar.set(1.0)
                        self.percent_label.configure(text="Processing\u2026")
                        self.speed_label.configure(text="")
                        self.eta_label.configure(text="")

                    elif d["status"] == "completed":
                        self._on_download_complete(d.get("output_path", ""))
                        return

                    elif d["status"] == "error":
                        self._on_download_error(d.get("message", "Unknown error"))
                        return

            except queue.Empty:
                pass

        finally:
            # Always reschedule — this also fires after return above,
            # so the polling chain never breaks between downloads.
            self.after(100, self._poll_queue)

    # ── progress display updates ────────────────────────

    def _update_progress(self, percent: float, speed: float, eta: float) -> None:
        self.progress_bar.set(min(percent / 100.0, 1.0))
        self.percent_label.configure(text=f"{percent:.1f}%")

        if speed:
            self.speed_label.configure(text=f"{format_bytes(speed)}/s")
        else:
            self.speed_label.configure(text="")

        if eta:
            self.eta_label.configure(text=f"{format_eta(eta)} remaining")
        else:
            self.eta_label.configure(text="")

    def _show_progress_section(self) -> None:
        self.progress_frame.grid(row=5, column=0, padx=30, pady=(0, 12), sticky="ew")

    def _hide_progress_section(self) -> None:
        self.progress_frame.grid_remove()

    def _reset_progress(self) -> None:
        self.progress_bar.set(0)
        self.percent_label.configure(text="")
        self.speed_label.configure(text="")
        self.eta_label.configure(text="")

    # ── download completion / error ─────────────────────

    def _on_download_complete(self, output_path: str) -> None:
        self.download_in_progress = False
        self.download_btn.configure(text="Download", state="normal")
        self.progress_bar.set(1.0)
        self.percent_label.configure(text="100%")
        self.speed_label.configure(text="Complete")
        self.eta_label.configure(text="")

        # Clear the message label — the popup replaces it
        self._clear_message()

        path_ok = bool(output_path) and os.path.exists(output_path)

        if path_ok:
            # Attempt trimming before showing the popup
            trimmed = self._trim_video(output_path)
            self.last_output_path = trimmed if trimmed else output_path
            self.play_btn.grid(
                row=7,
                column=0,
                padx=30,
                pady=(4, 0),
                sticky="w",
            )
        else:
            self.last_output_path = ""
            self.play_btn.grid_remove()

        # Show popup with a catch-all fallback
        try:
            if path_ok:
                self._show_success_popup(output_path)
            else:
                self._show_success_popup("")
        except Exception:
            # If the popup itself fails for any reason, fall back to the
            # inline message label so the user still sees feedback.
            if path_ok:
                self._show_message("Download completed successfully.", error=False)
            else:
                self._show_message(
                    "Download completed, but file was not found.", error=True
                )

    # ── success popup (CTkToplevel) ─────────────────────

    def _show_success_popup(self, filepath: str) -> None:
        """Display a non-blocking, topmost completion popup.

        If *filepath* is empty or the file is missing, a simplified popup
        is shown without file-specific details.
        """
        file_exists = bool(filepath) and os.path.exists(filepath)

        # --- metadata for display ---
        if file_exists:
            filename = os.path.basename(filepath)
            display_name = filename if len(filename) <= 55 else filename[:52] + "..."
            saved_dir = os.path.dirname(filepath)
            short_dir = saved_dir.replace(os.path.expanduser("~"), "~")
        else:
            display_name = ""
            short_dir = ""

        # --- build popup ---
        popup = ctk.CTkToplevel(self)
        popup.title("Download Complete")
        popup.attributes("-topmost", True)
        popup.transient(self)
        popup.grab_set()
        popup.focus_set()
        popup.protocol("WM_DELETE_WINDOW", popup.destroy)

        # Derive height: with file info → 260, generic → 190
        has_info = bool(display_name)
        pw, ph = (400, 270 if has_info else 190)
        popup.resizable(False, False)
        self.center_window(pw, ph, window=popup)

        # --- layout ---
        popup.grid_columnconfigure(0, weight=1)

        # Icon (safe lookup)
        try:
            icon_img = self.icons.get("download")
        except Exception:
            icon_img = None
        if icon_img:
            ctk.CTkLabel(
                popup,
                text="",
                image=icon_img,
                fg_color="transparent",
                bg_color="transparent",
            ).grid(row=0, column=0, pady=(28, 8))

        # Heading
        ctk.CTkLabel(
            popup,
            text="Download Completed",
            font=self._font(18, "bold"),
            bg_color="transparent",
        ).grid(row=1, column=0, padx=30, pady=(0, 2))

        if has_info:
            # Filename
            ctk.CTkLabel(
                popup,
                text=display_name,
                font=self._font(13),
                text_color=("gray50", "gray60"),
                wraplength=340,
                bg_color="transparent",
            ).grid(row=2, column=0, padx=30, pady=(0, 2))

            # Directory
            ctk.CTkLabel(
                popup,
                text=f"Saved to  {short_dir}",
                font=self._font(11),
                text_color=("gray45", "gray55"),
                wraplength=340,
                bg_color="transparent",
            ).grid(row=3, column=0, padx=30, pady=(0, 20))

            # --- buttons (with file info) ---
            btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
            btn_frame.grid(row=4, column=0, padx=30, pady=(0, 22))

            def _play_and_close() -> None:
                popup.destroy()
                self._play_video()

            play_btn = ctk.CTkButton(
                btn_frame,
                text="Play",
                width=110,
                height=36,
                corner_radius=8,
                border_width=1,
                border_color=("#1A6AE0", "#0A6AE0"),
                fg_color=("#2979FF", "#0A84FF"),
                hover_color=("#1A6AE0", "#0073E0"),
                font=self._font(13, "bold"),
                image=self.icons.get("play"),
                compound="left",
                command=_play_and_close,
            )
            play_btn.pack(side="left", padx=(0, 8))

            dismiss_btn = ctk.CTkButton(
                btn_frame,
                text="Dismiss",
                width=110,
                height=36,
                corner_radius=8,
                border_width=1,
                border_color=("gray82", "gray35"),
                fg_color=("gray88", "gray28"),
                hover_color=("gray78", "gray35"),
                text_color=("gray15", "gray85"),
                font=self._font(13),
                command=popup.destroy,
            )
            dismiss_btn.pack(side="left", padx=(8, 0))

            # Keyboard shortcuts
            popup.bind("<Return>", lambda _: _play_and_close())
            popup.bind("<Escape>", lambda _: popup.destroy())

        else:
            # Generic popup — no file details, just Dismiss
            ctk.CTkLabel(
                popup,
                text="Your download has finished successfully.",
                font=self._font(13),
                text_color=("gray50", "gray60"),
                wraplength=320,
                bg_color="transparent",
            ).grid(row=2, column=0, padx=30, pady=(12, 20))

            dismiss_btn = ctk.CTkButton(
                popup,
                text="Dismiss",
                width=120,
                height=36,
                corner_radius=8,
                border_width=1,
                border_color=("gray82", "gray35"),
                fg_color=("gray88", "gray28"),
                hover_color=("gray78", "gray35"),
                text_color=("gray15", "gray85"),
                font=self._font(13),
                command=popup.destroy,
            )
            dismiss_btn.grid(row=3, column=0, pady=(0, 20))

    # ── video trimming (FFmpeg stream copy) ────────────

    def _trim_video(self, input_path: str) -> str | None:
        """Trim the downloaded file if the user entered start/end times.

        Uses ``ffmpeg -c copy`` (stream copy) so the operation is near
        instantaneous and lossless.  The original file is **replaced**
        in-place with the trimmed version.

        Returns the final path (same as *input_path* on success,
        *input_path* unchanged on skip/failure, or ``None`` if the
        file disappeared).
        """
        if not input_path or not os.path.isfile(input_path):
            return None

        start_raw = self.trim_start_entry.get().strip()
        end_raw = self.trim_end_entry.get().strip()

        if not start_raw and not end_raw:
            return input_path  # nothing to trim

        if not shutil.which("ffmpeg"):
            self._show_message(
                "FFmpeg is required for trimming. Install FFmpeg and retry.",
                error=True,
            )
            return input_path

        # Validate time formats
        start = parse_time(start_raw)
        if start_raw and start is None:
            self._show_message("Invalid trim Start time. Use HH:MM:SS.", error=True)
            return input_path

        end = parse_time(end_raw)
        if end_raw and end is None:
            self._show_message("Invalid trim End time. Use HH:MM:SS.", error=True)
            return input_path

        # Build FFmpeg command — stream copy (-c copy) for speed
        cmd = ["ffmpeg", "-y"]
        if start is not None:
            cmd.extend(["-ss", start_raw])
        cmd.extend(["-i", input_path])
        if end is not None:
            cmd.extend(["-to", end_raw])
        cmd.extend(["-c", "copy", input_path])

        # Show trim status on progress bar
        self.progress_bar.set(1.0)
        self.percent_label.configure(text="Trimming\u2026")
        self.speed_label.configure(text="")
        self.eta_label.configure(text="")
        self.update_idletasks()

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
                self._show_message(
                    f"Trim failed: {err_tail}",
                    error=True,
                )
                return input_path

            if not os.path.isfile(input_path) or os.path.getsize(input_path) == 0:
                self._show_message(
                    "Trim produced an empty file. Keeping original.",
                    error=True,
                )
                return input_path

            # Restore the 100 % label
            self.percent_label.configure(text="100%")
            self.speed_label.configure(text="Complete")
            return input_path

        except subprocess.TimeoutExpired:
            if proc is not None:
                proc.kill()
            self._show_message("Trim timed out after 5 minutes.", error=True)
            return input_path
        except Exception as exc:
            self._show_message(
                f"Trim error: {str(exc)[:120]}",
                error=True,
            )
            return input_path

    def _on_download_error(self, message: str) -> None:
        self.download_in_progress = False
        self.download_btn.configure(text="Download", state="normal")
        self._reset_progress()
        self._show_message(message, error=True)

    # ── messaging ───────────────────────────────────────

    def _show_message(self, text: str, *, error: bool = False) -> None:
        self.message_label.configure(
            text=text,
            text_color=("#FF3B30" if error else "#34C759"),
        )

    def _clear_message(self) -> None:
        self.message_label.configure(text="")

    # ── media playback ──────────────────────────────────

    def _play_video(self) -> None:
        if not self.last_output_path or not os.path.exists(self.last_output_path):
            return
        try:
            if shutil.which("mpv"):
                subprocess.Popen(
                    ["mpv", self.last_output_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.last_output_path])
            elif sys.platform == "win32":
                os.startfile(self.last_output_path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", self.last_output_path])
        except Exception:
            pass  # best-effort


# ═══════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════


def main() -> None:
    # ── High-DPI support (Windows) ──
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    # ── Performance / rendering hints ──
    try:
        import tkinter as tk

        root = tk.Tk()
        scaling = root.winfo_pixels("1i") / 72.0
        if scaling > 1.25:
            ctk.set_widget_scaling(scaling)
            ctk.set_window_scaling(scaling)
        else:
            ctk.set_widget_scaling(1.0)
            ctk.set_window_scaling(1.0)
        root.destroy()
    except Exception:
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
