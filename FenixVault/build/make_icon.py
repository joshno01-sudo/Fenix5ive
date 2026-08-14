#!/usr/bin/env python3
"""Generate fenixvault.ico with no image-library dependency.

The .ico is committed alongside this script, so a normal build never has to run
it. Re-run it only when the mark itself changes::

    python build/make_icon.py

Draws a phoenix flame -- a cone sitting on a disc, with a gold core -- on the
dark tile from the app header, at every size Windows asks for. Coverage is
computed by 4x4 supersampling because a 16x16 icon lives or dies on its edges.
"""

from __future__ import annotations

import math
import os
import struct

SIZES = (16, 24, 32, 48, 64, 128, 256)

BACKDROP = (0x15, 0x17, 0x1C)   # header charcoal
FLAME = (0xE2, 0x52, 0x1A)      # fire orange
CORE = (0xF2, 0xA0, 0x3D)       # gold
SAMPLES = 4                     # per axis


def _blend(under: tuple[int, int, int], over: tuple[int, int, int],
           alpha: float) -> tuple[int, int, int]:
    return tuple(round(u + (o - u) * alpha) for u, o in zip(under, over))  # type: ignore


def _rounded_tile(x: float, y: float, size: float) -> bool:
    """Squircle-ish tile with a corner radius of a sixth of the side."""
    radius = size / 6.0
    left, top, right, bottom = 0.0, 0.0, size, size
    cx = min(max(x, left + radius), right - radius)
    cy = min(max(y, top + radius), bottom - radius)
    return math.hypot(x - cx, y - cy) <= radius or (
        left + radius <= x <= right - radius) or (
        top + radius <= y <= bottom - radius)


def _flame(x: float, y: float, size: float, scale: float = 1.0) -> bool:
    """A cone tapering to a point, resting on a disc."""
    cx = size * 0.5
    disc_y = size * 0.655
    radius = size * 0.255 * scale
    tip_y = size * (0.655 - 0.515 * scale)

    if math.hypot(x - cx, y - disc_y) <= radius:
        return True
    if tip_y <= y < disc_y:
        span = radius * (y - tip_y) / (disc_y - tip_y)
        # Curve the sides in slightly so the cone reads as a flame, not a wedge.
        span *= 0.55 + 0.45 * ((y - tip_y) / (disc_y - tip_y)) ** 0.5
        return abs(x - cx) <= span
    return False


def _coverage(px: int, py: int, size: int, shape) -> float:
    hits = 0
    step = 1.0 / SAMPLES
    for sy in range(SAMPLES):
        for sx in range(SAMPLES):
            x = px + (sx + 0.5) * step
            y = py + (sy + 0.5) * step
            if shape(x, y, float(size)):
                hits += 1
    return hits / (SAMPLES * SAMPLES)


def render(size: int) -> bytes:
    """32-bit BGRA pixels, bottom-up, as Windows icons store them."""
    rows: list[bytes] = []
    for py in range(size):
        row = bytearray()
        for px in range(size):
            tile = _coverage(px, py, size, _rounded_tile)
            if tile <= 0.0:
                row += bytes((0, 0, 0, 0))
                continue
            colour = BACKDROP
            flame = _coverage(px, py, size, lambda x, y, s: _flame(x, y, s))
            if flame > 0:
                colour = _blend(colour, FLAME, flame)
            core = _coverage(px, py, size,
                             lambda x, y, s: _flame(x, y + s * 0.055, s, 0.46))
            if core > 0:
                colour = _blend(colour, CORE, core)
            red, green, blue = colour
            row += bytes((blue, green, red, round(255 * tile)))
        rows.append(bytes(row))
    return b"".join(reversed(rows))


def image_blob(size: int) -> bytes:
    pixels = render(size)
    mask_row = ((size + 31) // 32) * 4      # 1bpp rows pad to 4 bytes
    mask = b"\x00" * (mask_row * size)      # alpha does the masking
    header = struct.pack(
        "<IiiHHIIiiII",
        40,             # header size
        size,           # width
        size * 2,       # height: colour plane plus mask plane
        1,              # planes
        32,             # bits per pixel
        0,              # BI_RGB
        len(pixels) + len(mask),
        0, 0, 0, 0,
    )
    return header + pixels + mask


def build(path: str) -> None:
    blobs = [image_blob(size) for size in SIZES]
    offset = 6 + 16 * len(blobs)
    out = bytearray(struct.pack("<HHH", 0, 1, len(blobs)))
    for size, blob in zip(SIZES, blobs):
        out += struct.pack("<BBBBHHII",
                           0 if size >= 256 else size,
                           0 if size >= 256 else size,
                           0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    for blob in blobs:
        out += blob
    with open(path, "wb") as handle:
        handle.write(bytes(out))
    print(f"wrote {path} ({len(out):,} bytes, sizes {', '.join(map(str, SIZES))})")


if __name__ == "__main__":
    build(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fenixvault.ico"))
