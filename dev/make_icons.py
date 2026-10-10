"""Generate icon.ico from desktop/icon.png with the sizes Windows asks for.

Windows requests small icon sizes for the taskbar (16/20/24/32) and the
window, and large ones elsewhere. A single 256x256 entry gives it nothing to
use at 16-32px. This writes a proper multi-size .ico: classic BMP entries for
the small sizes and PNG for the two largest.

Uses Qt, which is already a dependency, so there is nothing extra to install.

    .venv\\Scripts\\python.exe dev\\make_icons.py
"""

import os
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

SOURCE = os.path.join(ROOT, "desktop", "icon.png")
TARGET = os.path.join(ROOT, "icon.ico")

# Small sizes as BMP, the two biggest as PNG. 16/24/32 are what the taskbar
# and title bar actually ask for, so they must exist as real entries.
SIZES_BMP = (16, 20, 24, 32, 40, 48, 64)
SIZES_PNG = (128, 256)


def bmp_entry(img):
    """A 32bpp bottom-up DIB plus a fully-opaque AND mask, as ICO expects."""
    w, h = img.width(), img.height()
    rows = []
    for y in range(h - 1, -1, -1):
        row = bytearray()
        for x in range(w):
            c = img.pixelColor(x, y)
            row += bytes((c.blue(), c.green(), c.red(), c.alpha()))
        rows.append(bytes(row))
    xor = b"".join(rows)
    # AND mask rows are 1bpp and padded to 4 bytes; all zero because the
    # alpha channel in the XOR data does the real work.
    mask_stride = ((w + 31) // 32) * 4
    mask = b"\x00" * (mask_stride * h)
    header = struct.pack(
        "<IiiHHIIiiII",
        40,             # biSize
        w,              # biWidth
        h * 2,          # biHeight: XOR image + AND mask
        1,              # biPlanes
        32,             # biBitCount
        0,              # biCompression = BI_RGB
        len(xor) + len(mask),
        0, 0, 0, 0,
    )
    return header + xor + mask


def png_entry(img):
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(buf.data())


def main():
    app = QApplication.instance() or QApplication([])

    source = QImage(SOURCE)
    if source.isNull():
        raise SystemExit(f"could not read {SOURCE}")
    source = source.convertToFormat(QImage.Format_ARGB32)
    print(f"source: {SOURCE} ({source.width()}x{source.height()})")

    entries = []
    for size in SIZES_BMP:
        scaled = source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        entries.append((size, scaled, bmp_entry(scaled), "BMP"))
    for size in SIZES_PNG:
        scaled = source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        entries.append((size, scaled, png_entry(scaled), "PNG"))

    # ICONDIR + ICONDIRENTRY table + payloads
    offset = 6 + 16 * len(entries)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
    payloads = bytearray()
    for size, _img, data, _kind in entries:
        directory += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,   # 0 means 256 in an ICO entry
            size if size < 256 else 0,
            0, 0, 1, 32, len(data), offset,
        )
        payloads += data
        offset += len(data)

    with open(TARGET, "wb") as handle:
        handle.write(directory)
        handle.write(payloads)

    print(f"wrote {TARGET} ({os.path.getsize(TARGET):,} bytes)")
    for size, _img, data, kind in entries:
        print(f"  {size:>3}x{size:<3} {kind:<3} {len(data):>7,} bytes")


if __name__ == "__main__":
    main()
