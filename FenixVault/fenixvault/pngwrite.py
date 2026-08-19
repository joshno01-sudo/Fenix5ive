"""A minimal PNG encoder.

Screenshots are the one part of the snapshot that needs an image format, and
pulling in Pillow for it would add a large dependency to a program whose whole
selling point is that it is one self-contained file you can copy onto a USB
stick. PNG is simple enough to write directly: a header, zlib-compressed
scanlines, and a CRC per chunk.

Only what is actually needed is implemented -- 8-bit RGB and RGBA, no
interlacing, no palettes.
"""

from __future__ import annotations

import struct
import zlib
from binascii import crc32

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

COLOUR_RGB = 2
COLOUR_RGBA = 6

# Filter 0 (None) leaves the work to zlib. The per-byte alternatives (Sub, Up,
# Paeth) compress a screenshot better but cost seconds of pure-Python looping
# over several million pixels, which is the wrong trade for a backup that the
# user is waiting on.
FILTER_NONE = 0


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", crc32(kind + data) & 0xFFFFFFFF))


def encode_png(width: int, height: int, pixels: bytes, channels: int = 3,
               compress_level: int = 6) -> bytes:
    """Encode raw top-down pixel data as a PNG.

    *pixels* must be ``width * height * channels`` bytes, row-major and
    top-down, RGB or RGBA.
    """
    if channels not in (3, 4):
        raise ValueError("channels must be 3 (RGB) or 4 (RGBA)")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    stride = width * channels
    expected = stride * height
    if len(pixels) != expected:
        raise ValueError(
            f"expected {expected} bytes of pixel data, got {len(pixels)}")

    raw = bytearray()
    for row in range(height):
        start = row * stride
        raw.append(FILTER_NONE)
        raw += pixels[start:start + stride]

    header = struct.pack(">IIBBBBB", width, height, 8,
                         COLOUR_RGB if channels == 3 else COLOUR_RGBA,
                         0, 0, 0)
    return (PNG_SIGNATURE
            + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), compress_level))
            + _chunk(b"IEND", b""))


def write_png(path: str, width: int, height: int, pixels: bytes,
              channels: int = 3) -> None:
    with open(path, "wb") as handle:
        handle.write(encode_png(width, height, pixels, channels))


def bgra_to_rgb(bgra: bytes) -> bytes:
    """Convert the BGRA buffer Windows hands back into plain RGB.

    Done with whole-slice operations rather than a loop, because a 4K screen is
    over eight million pixels and a per-pixel loop in Python would take longer
    than the rest of the backup.
    """
    raw = bytearray(bgra)
    del raw[3::4]                      # drop alpha, leaving BGR
    blue = bytes(raw[0::3])
    raw[0::3] = raw[2::3]              # red into the first slot
    raw[2::3] = blue                   # blue into the third
    return bytes(raw)
