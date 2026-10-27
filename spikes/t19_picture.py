"""T19 probe: capture the view window of a model (copy of LIRA example 01) as PNG.

Tries PrintWindow with PW_RENDERFULLCONTENT; saves spikes/out/t19_view.png.
"""

import shutil
import struct
import time
import zlib
from pathlib import Path

import win32con
import win32gui
import win32ui

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install

MANUAL = Path(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU")
OUT = Path(__file__).parent / "out"
SRC = next((MANUAL / "01_плоская рама ЖБ").glob("*.lir"))


def png(width: int, height: int, bgra: bytes) -> bytes:
    rows = b"".join(
        b"\x00" + bytes(px for i in range(0, width * 4, 4) for px in
                        (row[i + 2], row[i + 1], row[i]))
        for row in (bgra[y * width * 4:(y + 1) * width * 4] for y in range(height))
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def capture(hwnd: int) -> tuple[int, int, bytes]:
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    w, h = right - left, bottom - top
    hdc = win32gui.GetWindowDC(hwnd)
    src = win32ui.CreateDCFromHandle(hdc)
    mem = src.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(src, w, h)
    mem.SelectObject(bmp)
    import ctypes

    ok = ctypes.windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), 1 | 2)  # client | full content
    bits = bmp.GetBitmapBits(True)
    mem.DeleteDC()
    src.DeleteDC()
    win32gui.ReleaseDC(hwnd, hdc)
    win32gui.DeleteObject(bmp.GetHandle())
    print("PrintWindow:", ok, "size", w, h)
    return w, h, bits


adapter = ComLiraAdapter(pick_install(find_installs(), None))
adapter.connect()
try:
    copy = OUT / "t19_ex01.lir"
    shutil.copy(SRC, copy)
    info, _ = adapter.open_document(str(copy))
    doc = adapter.find_document(info.path)
    doc.Activate()
    adapter._app.StartCmd(5249)  # isometric
    adapter._app.StartCmd(5085)  # fit in window
    time.sleep(1.0)
    main = adapter._app  # noqa: F841
    found = []

    def visit(hwnd, _):
        if win32gui.GetClassName(hwnd) == "MDIClient":
            found.append(hwnd)

    def tops(hwnd, _):
        if "ЛИРА" in win32gui.GetWindowText(hwnd) or "LIRA" in win32gui.GetWindowText(hwnd):
            win32gui.EnumChildWindows(hwnd, visit, None)

    win32gui.EnumWindows(tops, None)
    mdi = found[0]
    children = []
    win32gui.EnumChildWindows(mdi, lambda h, _: children.append(h), None)
    for c in children[:12]:
        print(c, win32gui.GetClassName(c), repr(win32gui.GetWindowText(c)),
              win32gui.GetParent(c) == mdi, win32gui.GetClientRect(c))
    frames = [c for c in children if win32gui.GetParent(c) == mdi]
    frame = next(c for c in frames if "t19_ex01" in win32gui.GetWindowText(c))
    views = []
    win32gui.EnumChildWindows(frame, lambda h, _: views.append(h), None)
    target = max(views or [frame], key=lambda h: (lambda r: r[2] * r[3])(win32gui.GetClientRect(h)))
    print("target", target, win32gui.GetClassName(target))
    w, h, bits = capture(target)
    (OUT / "t19_view.png").write_bytes(png(w, h, bits))
    nonwhite = sum(1 for i in range(0, len(bits), 4) if bits[i:i + 3] != b"\xff\xff\xff")
    print("non-white pixels:", nonwhite, "of", w * h)
    adapter.close_document(info.path, True)
finally:
    adapter.disconnect()
