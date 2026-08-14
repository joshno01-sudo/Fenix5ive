"""Screenshots of the desktop, straight out of GDI.

Before wiping a PC it is worth having a picture of what it looked like: where
the icons were, what was pinned to the taskbar, which windows were open. None
of that survives in any settings export, and it is the fastest way to answer
"what was I running?" a week later.

Everything here goes through ctypes against user32/gdi32, so there is no
imaging dependency. On anything other than Windows the capture functions return
an empty list rather than raising, which keeps the snapshot code
platform-neutral and testable.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

from .pngwrite import bgra_to_rgb, write_png

IS_WINDOWS = os.name == "nt"

SRCCOPY = 0x00CC0020
# Without CAPTUREBLT, layered windows (many modern apps, tooltips, some of the
# taskbar) come out as holes in the image.
CAPTUREBLT = 0x40000000
DIB_RGB_COLORS = 0

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# SetThreadDpiAwarenessContext(-4) = PER_MONITOR_AWARE_V2. Scoped to this
# thread on purpose: making the whole process DPI-aware would change how Tk
# lays the window out, and we only need true pixels for the duration of a grab.
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

MAX_DIMENSION = 30000     # sanity bound; a bad metric should not allocate 40 GB

# MonitorEnumProc, exactly as Windows declares it. The final parameter is an
# LPARAM -- a pointer-sized integer. Declaring it as anything else (a double,
# say) puts it in the wrong register class on x64 and every call from that
# point on is undefined. Kept at module scope so a test can assert the shape.
if os.name == "nt":
    MONITOR_ENUM_PROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,                    # BOOL return
        ctypes.c_void_p,                  # HMONITOR
        ctypes.c_void_p,                  # HDC
        ctypes.POINTER(wintypes.RECT),    # LPRECT
        wintypes.LPARAM)                  # LPARAM
else:                                     # pragma: no cover - shape only
    MONITOR_ENUM_PROC = None


@dataclass
class Shot:
    name: str
    width: int
    height: int
    rgb: bytes

    @property
    def megapixels(self) -> float:
        return (self.width * self.height) / 1_000_000.0


@dataclass
class MonitorInfo:
    name: str
    left: int
    top: int
    right: int
    bottom: int
    primary: bool

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def describe(self) -> str:
        role = "primary" if self.primary else "secondary"
        return (f"{self.name}  {self.width}x{self.height} at "
                f"({self.left},{self.top})  [{role}]")


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32)]


class _DpiScope:
    """Per-thread DPI awareness, restored on the way out."""

    def __init__(self) -> None:
        self._previous = None

    def __enter__(self) -> "_DpiScope":
        if not IS_WINDOWS:
            return self
        try:
            user32 = ctypes.windll.user32
            user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
            user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            self._previous = user32.SetThreadDpiAwarenessContext(
                DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        except (AttributeError, OSError):
            # Older Windows: we simply capture at the scaled resolution.
            self._previous = None
        return self

    def __exit__(self, *_exc) -> None:
        if IS_WINDOWS and self._previous:
            try:
                ctypes.windll.user32.SetThreadDpiAwarenessContext(self._previous)
            except (AttributeError, OSError):
                pass


def list_monitors() -> list[MonitorInfo]:
    """Every attached display, with its place in the virtual desktop."""
    if not IS_WINDOWS:
        return []
    monitors: list[MonitorInfo] = []
    user32 = ctypes.windll.user32

    callback_type = MONITOR_ENUM_PROC

    def _callback(handle, _dc, _rect, _data):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if user32.GetMonitorInfoW(ctypes.c_void_p(handle), ctypes.byref(info)):
            monitors.append(MonitorInfo(
                name=info.szDevice or f"Display {len(monitors) + 1}",
                left=info.rcMonitor.left, top=info.rcMonitor.top,
                right=info.rcMonitor.right, bottom=info.rcMonitor.bottom,
                primary=bool(info.dwFlags & 1)))
        return 1

    # Handles are pointer-sized; without argtypes ctypes would narrow them to
    # 32 bits on a 64-bit build.
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                           callback_type, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL

    native = callback_type(_callback)
    with _DpiScope():
        try:
            user32.EnumDisplayMonitors(None, None, native, 0)
        except OSError:
            return []
    return monitors


def _grab(left: int, top: int, width: int, height: int) -> bytes | None:
    """BitBlt a region of the screen and return it as RGB bytes."""
    if width <= 0 or height <= 0 or width > MAX_DIMENSION or height > MAX_DIMENSION:
        return None
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    user32.GetDC.restype = ctypes.c_void_p
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
    gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                             ctypes.c_int]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    screen_dc = user32.GetDC(None)
    if not screen_dc:
        return None
    memory_dc = None
    bitmap = None
    try:
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        if not memory_dc or not bitmap:
            return None
        previous = gdi32.SelectObject(memory_dc, bitmap)
        ok = gdi32.BitBlt(ctypes.c_void_p(memory_dc), 0, 0, width, height,
                          ctypes.c_void_p(screen_dc), left, top,
                          SRCCOPY | CAPTUREBLT)
        if not ok:
            return None

        info = _BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height        # negative: top-down rows
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0         # BI_RGB

        buffer = ctypes.create_string_buffer(width * height * 4)
        copied = gdi32.GetDIBits(ctypes.c_void_p(memory_dc),
                                 ctypes.c_void_p(bitmap), 0, height, buffer,
                                 ctypes.byref(info), DIB_RGB_COLORS)
        gdi32.SelectObject(memory_dc, previous)
        if not copied:
            return None
        return bgra_to_rgb(buffer.raw)
    except OSError:
        return None
    finally:
        if bitmap:
            gdi32.DeleteObject(ctypes.c_void_p(bitmap))
        if memory_dc:
            gdi32.DeleteDC(ctypes.c_void_p(memory_dc))
        user32.ReleaseDC(None, ctypes.c_void_p(screen_dc))


def capture_all() -> list[Shot]:
    """One image of the whole desktop, plus one per monitor when there are several."""
    if not IS_WINDOWS:
        return []
    shots: list[Shot] = []
    with _DpiScope():
        try:
            metrics = ctypes.windll.user32.GetSystemMetrics
            left = metrics(SM_XVIRTUALSCREEN)
            top = metrics(SM_YVIRTUALSCREEN)
            width = metrics(SM_CXVIRTUALSCREEN)
            height = metrics(SM_CYVIRTUALSCREEN)
        except OSError:
            return []

        whole = _grab(left, top, width, height)
        if whole is not None:
            shots.append(Shot("desktop-all-screens", width, height, whole))

        monitors = list_monitors()
        if len(monitors) > 1:
            for index, monitor in enumerate(monitors, start=1):
                pixels = _grab(monitor.left, monitor.top,
                               monitor.width, monitor.height)
                if pixels is not None:
                    label = "primary" if monitor.primary else f"screen-{index}"
                    shots.append(Shot(f"desktop-{label}", monitor.width,
                                      monitor.height, pixels))
    return shots


def save_shots(shots: list[Shot], folder: str) -> list[str]:
    """Write each shot as a PNG. Returns the paths actually written."""
    os.makedirs(folder, exist_ok=True)
    written: list[str] = []
    for shot in shots:
        path = os.path.join(folder, f"{shot.name}.png")
        try:
            write_png(path, shot.width, shot.height, shot.rgb)
            written.append(path)
        except (OSError, ValueError):
            continue
    return written
