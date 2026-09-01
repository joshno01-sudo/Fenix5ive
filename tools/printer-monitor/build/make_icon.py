#!/usr/bin/env python3
"""Generate printermonitor.ico with no image-library dependency.

The .ico is committed next to this script, so a normal build never runs it.
Re-run it only when the mark changes::

    python build/make_icon.py

Draws an ink drop, filled to a level, on the dark tile the rest of the Fenix
5ive tooling uses. A drop reads at 16x16 where a printer outline turns to mush,
and the fill line is the thing the program is actually about. Coverage is
computed by 4x4 supersampling, because a small icon lives or dies on its edges.
"""

from __future__ import annotations

import math
import os
import struct

SIZES = (16, 24, 32, 48, 64, 128, 256)

BACKDROP = (0x15, 0x17, 0x1C)  # header charcoal, shared with Fenix Vault
EMPTY = (0x3A, 0x3E, 0x47)     # the unfilled part of the drop
FLAME = (0xE2, 0x52, 0x1A)     # fire orange
CORE = (0xF2, 0xA0, 0x3D)      # gold
SAMPLES = 4                    # per axis

# How full the drop is drawn. Deliberately not full: the icon should look like
# a gauge with something to say, not a solid blob.
FILL_LEVEL = 0.62


def _blend(under, over, alpha):
    return tuple(round(u + (o - u) * alpha) for u, o in zip(under, over))


def _rounded_tile(x: float, y: float, size: float) -> bool:
    """Squircle-ish tile with a corner radius of a sixth of the side."""
    radius = size / 6.0
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    return math.hypot(x - cx, y - cy) <= radius


def _drop(x: float, y: float, size: float) -> bool:
    """A teardrop: a circle for the belly, a cone narrowing to the tip.

    Coordinates are in pixels; the drop is centred horizontally and inset so
    the tile still reads as a tile at small sizes.
    """
    inset = size * 0.20
    top = inset
    bottom = size - inset * 0.85
    height = bottom - top
    if height <= 0:
        return False

    centre_x = size / 2.0
    # Belly: a circle tangent to the bottom.
    belly_r = height * 0.36
    belly_y = bottom - belly_r
    if math.hypot(x - centre_x, y - belly_y) <= belly_r:
        return True

    # Cone: linear taper from the belly's widest point up to the tip.
    if y < top or y > belly_y:
        return False
    t = (y - top) / max(1e-6, belly_y - top)  # 0 at the tip, 1 at the belly
    half_width = belly_r * (t ** 0.72)
    return abs(x - centre_x) <= half_width


def _render(size: int) -> bytes:
    """One BGRA image, bottom-up, as an .ico expects."""
    step = 1.0 / SAMPLES
    rows = []
    fill_y = size * (1.0 - FILL_LEVEL)

    for py in range(size):
        row = bytearray()
        for px in range(size):
            tile_hits = 0
            drop_hits = 0
            filled_hits = 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x = px + (sx + 0.5) * step
                    y = py + (sy + 0.5) * step
                    if _rounded_tile(x, y, size):
                        tile_hits += 1
                    if _drop(x, y, size):
                        drop_hits += 1
                        if y >= fill_y:
                            filled_hits += 1

            total = SAMPLES * SAMPLES
            alpha = tile_hits / total
            if alpha == 0:
                row += b"\x00\x00\x00\x00"
                continue

            colour = BACKDROP
            drop_cover = drop_hits / total
            if drop_cover:
                filled_share = filled_hits / drop_hits if drop_hits else 0.0
                ink = _blend(FLAME, CORE, 0.35) if filled_share > 0.5 else EMPTY
                colour = _blend(colour, ink, drop_cover)

            # BGRA, premultiplied by nothing: Windows uses the alpha channel.
            row += bytes((colour[2], colour[1], colour[0], round(alpha * 255)))
        rows.append(bytes(row))

    # .ico bitmaps are stored bottom-up.
    pixels = b"".join(reversed(rows))

    # A DIB header claiming double the height: colour rows plus an AND mask.
    header = struct.pack(
        "<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0
    )
    mask_stride = ((size + 31) // 32) * 4
    mask = b"\x00" * (mask_stride * size)
    return header + pixels + mask


def build(path: str) -> None:
    images = [(size, _render(size)) for size in SIZES]

    offset = 6 + 16 * len(images)
    directory = b""
    body = b""
    for size, data in images:
        directory += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,  # 0 means 256
            size if size < 256 else 0,
            0,  # colours in palette
            0,  # reserved
            1,  # colour planes
            32,  # bits per pixel
            len(data),
            offset,
        )
        body += data
        offset += len(data)

    with open(path, "wb") as handle:
        handle.write(struct.pack("<HHH", 0, 1, len(images)))
        handle.write(directory)
        handle.write(body)


if __name__ == "__main__":
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "printermonitor.ico")
    build(target)
    print(f"wrote {target} ({os.path.getsize(target):,} bytes, sizes: "
          f"{', '.join(str(s) for s in SIZES)})")
