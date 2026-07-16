#!/usr/bin/env python3
"""
YVid — Modern Desktop Video Downloader
Built with CustomTkinter + yt-dlp + FFmpeg
"""

# ═══════════════════════════════════════════════════════════
#  IMPORTS
# ═══════════════════════════════════════════════════════════

from __future__ import annotations

import customtkinter as ctk
import yt_dlp
import threading
import queue
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from tkinter import filedialog, StringVar, BooleanVar
from PIL import Image, ImageDraw

# ═══════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════

APP_NAME = "YVid"
VERSION = "1.0.0"
WINDOW_WIDTH = 620
WINDOW_HEIGHT = 600
MIN_WIDTH = 580
MIN_HEIGHT = 520
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/Videos/YVid")
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
ICON_SCALE = 5  # Draw at 5× resolution for crisp downscaled anti-aliasing

FORMAT_VIDEO_QUALITY = {
    "Best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "2160p": "bestvideo[ext=mp4][height<=2160]+bestaudio[ext=m4a]/best[ext=mp4][height<=2160]/best",
    "1080p": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best",
    "720p": "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best",
    "480p": "bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[ext=mp4][height<=480]/best",
    "360p": "bestvideo[ext=mp4][height<=360]+bestaudio[ext=m4a]/best[ext=mp4][height<=360]/best",
}

ERROR_PATTERNS: list[tuple[str, str]] = [
    (r"HTTP Error 403", "Access denied. The video may be private or age-restricted."),
    (r"HTTP Error 429", "Request rate limited. Wait a moment and retry."),
    (r"HTTP Error 4\d\d", "Video not available (server returned {code})."),
    (r"HTTP Error 5\d\d", "Server error. The platform may be experiencing issues."),
    (r"Video unavailable", "This video has been removed or is unavailable."),
    (r"Private video", "This video is private. Sign-in is required."),
    (
        r"ffmpeg not found"
        r"|ffprobe not found",
        "FFmpeg is required. Install FFmpeg and try again.",
    ),
    (
        r"Connection refused"
        r"|ConnectionError"
        r"|Cannot connect",
        "Network error. Check your internet connection.",
    ),
    (r"SSL", "SSL connection error. Check your network or date settings."),
    (r"No video formats found", "No available formats found for this video."),
    (r"unsupported url", "Unsupported URL. Please enter a valid video URL."),
]

# ═══════════════════════════════════════════════════════════
#  FORMATTING HELPERS
# ═══════════════════════════════════════════════════════════


def format_bytes(n: float) -> str:
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
    if not seconds or seconds < 0:
        return "\u2014\u2014"
    s = int(seconds)
    if s < 60:
        return f"0:{s:02d}"
    if s < 3600:
        return f"{s // 60}:{s % 60:02d}"
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def is_valid_url(url: str) -> bool:
    url = url.strip()
    if not url:
        return False
    return bool(re.match(r"^https?://[^\s/$.?#].[^\s]*$", url))


def format_error_message(error_str: str) -> str:
    for pattern, message in ERROR_PATTERNS:
        match = re.search(pattern, error_str, re.IGNORECASE)
        if match:
            code = match.group(0) if match.lastgroup is None else ""
            return message.format(code=code)
    msg = error_str.strip()[:120]
    if len(error_str) > 120:
        msg += "\u2026"
    return f"Download failed: {msg}"


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


ICON_DEFS: dict[str, tuple[int, int, Callable]] = {
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
#  DOWNLOAD WORKER  (background thread)
# ═══════════════════════════════════════════════════════════


class DownloadThread(threading.Thread):
    """Runs yt-dlp in a daemon thread and pushes progress updates to a queue."""

    def __init__(self, url: str, ydl_opts: dict, progress_queue: queue.Queue) -> None:
        super().__init__(daemon=True)
        self.url = url
        self.ydl_opts = ydl_opts
        self.queue = progress_queue
        self._original_filename: str | None = None

    # ── public ──────────────────────────────────────────

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

    # ── internal ────────────────────────────────────────

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

    def _resolve_output_path(self) -> str:
        if not self._original_filename:
            return ""

        is_audio = any(
            pp.get("key") == "FFmpegExtractAudio"
            for pp in self.ydl_opts.get("postprocessors", [])
        )

        if is_audio:
            path = os.path.splitext(self._original_filename)[0] + ".mp3"
        else:
            path = self._original_filename

        if os.path.exists(path):
            return path

        # fallback — scan output directory
        outdir = os.path.dirname(self.ydl_opts.get("outtmpl", ""))
        if outdir and os.path.isdir(outdir):
            exts = {".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".ogg", ".opus", ".flac"}
            files = [
                os.path.join(outdir, f)
                for f in os.listdir(outdir)
                if os.path.splitext(f)[1].lower() in exts
            ]
            if files:
                return max(files, key=os.path.getmtime)

        return path


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

        # window
        self.title(f"{APP_NAME}  \u2014  Video Downloader")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        self._center_window()
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

        # build UI
        self._build_ui()
        self._settings_visible = True  # start expanded

        # start queue poller
        self.after(100, self._poll_queue)

    # ── window helpers ──────────────────────────────────

    def _center_window(self) -> None:
        self.update_idletasks()
        x = (self.winfo_screenwidth() - WINDOW_WIDTH) // 2
        y = (self.winfo_screenheight() - WINDOW_HEIGHT) // 2
        self.geometry(f"+{x}+{y}")

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

    # -- header ------------------------------------------

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=30, pady=(30, 24), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=APP_NAME,
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Video Downloader",
            font=ctk.CTkFont(size=13),
            text_color=("gray50", "gray60"),
        ).grid(row=1, column=0, sticky="w")

    # -- url input ---------------------------------------

    def _build_url_section(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, padx=30, pady=(0, 16), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Paste video URL here\u2026",
            height=42,
            corner_radius=10,
            font=ctk.CTkFont(size=14),
        )
        self.url_entry.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        # bind Enter key to download
        self.url_entry.bind("<Return>", lambda _: self._start_download())

        paste_icon = self.icons.get("paste")
        self.paste_btn = ctk.CTkButton(
            frame,
            text="Paste",
            width=88,
            height=42,
            corner_radius=10,
            font=ctk.CTkFont(size=13),
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

        # subtle separator
        ctk.CTkFrame(
            self.settings_header,
            height=1,
            fg_color=("gray85", "gray35"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkLabel(
            self.settings_header,
            text="Settings",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("gray50", "gray60"),
        ).grid(row=0, column=0, padx=(0, 6))

        self.settings_chevron = ctk.CTkButton(
            self.settings_header,
            text="",
            width=26,
            height=26,
            corner_radius=6,
            fg_color="transparent",
            hover_color=("gray85", "gray30"),
            image=self.icons.get("chevron_down"),
            command=self._toggle_settings,
        )
        self.settings_chevron.grid(row=0, column=1, sticky="e")

    # -- settings panel (collapsible) ---------------------

    def _build_settings_panel(self) -> None:
        sf = ctk.CTkFrame(self, corner_radius=12, fg_color=("gray97", "gray18"))
        sf.grid(row=3, column=0, padx=30, pady=(10, 16), sticky="ew")
        sf.grid_columnconfigure(1, weight=1)
        self.settings_frame = sf

        # ---- row 0: Format ----
        ctk.CTkLabel(
            sf,
            text="Format",
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=0, padx=(16, 12), pady=(16, 6), sticky="w")

        self.format_seg = ctk.CTkSegmentedButton(
            sf,
            values=["Video MP4", "Audio MP3"],
            command=self._on_format_change,
            font=ctk.CTkFont(size=12),
            corner_radius=8,
        )
        self.format_seg.grid(row=0, column=1, padx=(0, 16), pady=(16, 6), sticky="ew")
        self.format_seg.set("Video MP4")

        # ---- row 1: Quality + Appearance ----
        inner1 = ctk.CTkFrame(sf, fg_color="transparent")
        inner1.grid(row=1, column=0, columnspan=2, padx=0, pady=0, sticky="ew")
        inner1.grid_columnconfigure(1, weight=1)
        inner1.grid_columnconfigure(3, weight=1)

        self.quality_label = ctk.CTkLabel(
            inner1,
            text="Quality",
            font=ctk.CTkFont(size=13),
        )
        self.quality_label.grid(row=0, column=0, padx=(16, 6), pady=4, sticky="w")

        self.quality_menu = ctk.CTkOptionMenu(
            inner1,
            values=["Best", "2160p", "1080p", "720p", "480p", "360p"],
            font=ctk.CTkFont(size=12),
            corner_radius=8,
            variable=self.quality_var,
        )
        self.quality_menu.grid(row=0, column=1, padx=(0, 16), pady=4, sticky="ew")

        ctk.CTkLabel(
            inner1,
            text="Theme",
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=2, padx=(8, 6), pady=4, sticky="w")

        self.theme_menu = ctk.CTkOptionMenu(
            inner1,
            values=["System", "Light", "Dark"],
            font=ctk.CTkFont(size=12),
            corner_radius=8,
            command=self._change_theme,
        )
        self.theme_menu.grid(row=0, column=3, padx=(0, 16), pady=4, sticky="ew")
        self.theme_menu.set("System")

        # ---- row 2: Subtitles ----
        self.subs_check = ctk.CTkCheckBox(
            sf,
            text="Download subtitles (if available)",
            font=ctk.CTkFont(size=13),
            variable=self.subs_var,
            corner_radius=4,
            onvalue=True,
            offvalue=False,
        )
        self.subs_check.grid(
            row=2, column=0, columnspan=2, padx=(16, 16), pady=(4, 6), sticky="w"
        )

        # ---- row 3: Output ----
        ctk.CTkLabel(
            sf,
            text="Output",
            font=ctk.CTkFont(size=13),
        ).grid(row=3, column=0, padx=(16, 12), pady=(4, 16), sticky="w")

        out_frame = ctk.CTkFrame(sf, fg_color="transparent")
        out_frame.grid(row=3, column=1, padx=(0, 16), pady=(4, 16), sticky="ew")
        out_frame.grid_columnconfigure(0, weight=1)

        self.output_entry = ctk.CTkEntry(
            out_frame,
            textvariable=self.output_var,
            font=ctk.CTkFont(size=12),
            height=32,
            corner_radius=8,
            state="readonly",
        )
        self.output_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.browse_btn = ctk.CTkButton(
            out_frame,
            text="Browse",
            width=78,
            height=32,
            font=ctk.CTkFont(size=12),
            corner_radius=8,
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
            height=46,
            corner_radius=10,
            font=ctk.CTkFont(size=15, weight="bold"),
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
            font=ctk.CTkFont(size=14, weight="bold"),
            width=60,
            anchor="w",
        )
        self.percent_label.grid(row=0, column=0, sticky="w")

        self.speed_label = ctk.CTkLabel(
            stats,
            text="",
            font=ctk.CTkFont(size=13),
            anchor="center",
        )
        self.speed_label.grid(row=0, column=1, sticky="ew")

        self.eta_label = ctk.CTkLabel(
            stats,
            text="",
            font=ctk.CTkFont(size=13),
            anchor="e",
        )
        self.eta_label.grid(row=0, column=2, sticky="e")

        # hidden until download starts
        self.progress_frame.grid_remove()

    # -- message label -----------------------------------

    def _build_message_label(self) -> None:
        self.message_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=13),
            anchor="w",
        )
        self.message_label.grid(row=6, column=0, padx=30, pady=(0, 8), sticky="ew")

    # -- play button -------------------------------------

    def _build_play_btn(self) -> None:
        self.play_btn = ctk.CTkButton(
            self,
            text="Play with mpv",
            height=38,
            corner_radius=10,
            font=ctk.CTkFont(size=13),
            image=self.icons.get("play"),
            compound="left",
            command=self._play_video,
            fg_color=("gray85", "gray30"),
            text_color=("gray15", "gray85"),
            hover_color=("gray75", "gray40"),
        )
        # hidden after download completes
        self.play_btn.grid_remove()

    # ── settings toggle ─────────────────────────────────

    def _toggle_settings(self) -> None:
        if self._settings_visible:
            self.settings_frame.grid_remove()
            self.settings_chevron.configure(image=self.icons.get("chevron_up"))
            self._settings_visible = False
        else:
            self.settings_frame.grid()
            self.settings_chevron.configure(image=self.icons.get("chevron_down"))
            self._settings_visible = True

    def _on_format_change(self, value: str) -> None:
        if value == "Audio MP3":
            self.quality_label.grid_remove()
            self.quality_menu.grid_remove()
            self.subs_check.grid_remove()
        else:
            self.quality_label.grid()
            self.quality_menu.grid()
            self.subs_check.grid()

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
        directory = filedialog.askdirectory(
            title="Select Download Directory",
            initialdir=self.output_var.get() or DEFAULT_OUTPUT_DIR,
            parent=self,
        )
        if directory:
            self.output_var.set(directory)

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
        if not self.download_in_progress:
            self.after(100, self._poll_queue)
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

        self._show_message("Download complete!", error=False)

        if output_path and os.path.exists(output_path):
            self.last_output_path = output_path
            self.play_btn.grid(row=7, column=0, padx=30, pady=(4, 0), sticky="w")
        else:
            self.last_output_path = ""
            self.play_btn.grid_remove()

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
    ctk.set_widget_scaling(1.0)
    ctk.set_window_scaling(1.0)

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
