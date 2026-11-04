#!/usr/bin/env python3
"""Gera ui/Nexus.App/Assets/nexus.ico (monograma "N") só com a biblioteca padrão.

    python scripts/make_icon.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "ui" / "Nexus.App" / "Assets" / "nexus.ico"
BG = (11, 15, 20)
BLUE = (47, 129, 247)
CYAN = (43, 183, 201)
SIZES = (16, 32, 48, 64, 128, 256)
SS = 4  # supersampling para suavizar as bordas


def inside_rounded_square(x: float, y: float, radius: float = 0.2) -> bool:
    if not (0 <= x <= 1 and 0 <= y <= 1):
        return False
    cx = min(max(x, radius), 1 - radius)
    cy = min(max(y, radius), 1 - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def color_at(x: float, y: float) -> tuple[int, int, int, int]:
    if not inside_rounded_square(x, y):
        return (0, 0, 0, 0)
    left, right, top, bottom, bar = 0.26, 0.74, 0.24, 0.76, 0.11
    in_left = left <= x <= left + bar and top <= y <= bottom
    in_right = right - bar <= x <= right and top <= y <= bottom
    # diagonal do canto superior esquerdo ao inferior direito
    t = (y - top) / (bottom - top)
    diag_x = left + t * ((right - bar) - left)
    in_diag = top <= y <= bottom and diag_x <= x <= diag_x + bar * 1.15
    if in_left or in_right or in_diag:
        return (*BLUE, 255)
    if (x - 0.80) ** 2 + (y - 0.20) ** 2 <= 0.045 ** 2:  # ponto ciano discreto
        return (*CYAN, 255)
    return (*BG, 255)


def render(size: int) -> bytes:
    rows = []
    for py in range(size):
        row = bytearray([0])  # filtro PNG "nenhum"
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(SS):
                for sx in range(SS):
                    r, g, b, a = color_at((px + (sx + 0.5) / SS) / size, (py + (sy + 0.5) / SS) / size)
                    acc[0] += r * a; acc[1] += g * a; acc[2] += b * a; acc[3] += a
            total = SS * SS
            alpha = acc[3] / total
            if acc[3]:
                row += bytes((round(acc[0] / acc[3]), round(acc[1] / acc[3]), round(acc[2] / acc[3]), round(alpha)))
            else:
                row += bytes((0, 0, 0, 0))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main() -> None:
    images = [(size, render(size)) for size in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(header + entries + blobs)
    print(f"{OUT} ({OUT.stat().st_size} bytes, tamanhos {SIZES})")


if __name__ == "__main__":
    main()
