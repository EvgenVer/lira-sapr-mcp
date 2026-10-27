"""A picture of a model: LIRA's view window captured through Win32, saved as PNG.

LIRA's API has no picture export, and copying the view to the clipboard would overwrite
the user's clipboard, so the server asks the view window to draw itself into a bitmap
(PrintWindow) and encodes the PNG itself with zlib.
"""

import ctypes
import struct
import zlib

# PrintWindow flags: the client area only, and content drawn by the GPU as well.
PW_CLIENTONLY, PW_RENDERFULLCONTENT = 1, 2
DPI_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
WHITE = b"\xff\xff\xff"


def capture_window(hwnd: int) -> tuple[int, int, bytes]:
    """Width, height and the BGRA pixels (top row first) of a window's client area.

    The thread is made DPI-aware for the capture: otherwise, with display scaling, Windows
    reports a scaled-down size and the bitmap holds only the top-left part of the view.
    """
    user32 = ctypes.windll.user32
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p  # a handle, not an int
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    previous = user32.SetThreadDpiAwarenessContext(DPI_PER_MONITOR_AWARE_V2)
    try:
        return _capture(hwnd)
    finally:
        if previous:
            user32.SetThreadDpiAwarenessContext(previous)


def _capture(hwnd: int) -> tuple[int, int, bytes]:
    import win32gui
    import win32ui

    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise ValueError("the view window has no visible area (is LIRA minimized?)")
    window_dc = win32gui.GetWindowDC(hwnd)
    source = win32ui.CreateDCFromHandle(window_dc)
    memory = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(source, width, height)
        memory.SelectObject(bitmap)
        flags = PW_CLIENTONLY | PW_RENDERFULLCONTENT
        if not ctypes.windll.user32.PrintWindow(hwnd, memory.GetSafeHdc(), flags):
            raise ValueError("Windows could not draw LIRA's view window")
        return width, height, bitmap.GetBitmapBits(True)
    finally:
        memory.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(hwnd, window_dc)
        win32gui.DeleteObject(bitmap.GetHandle())


def crop(width: int, height: int, bgra: bytes, margin: int = 12) -> tuple[int, int, bytes]:
    """Cut the white border around the drawing, keeping ``margin`` pixels."""
    stride = width * 4
    rows = [bgra[y * stride : (y + 1) * stride] for y in range(height)]
    used_rows = [y for y, row in enumerate(rows) if _inked(row)]
    if not used_rows:
        return width, height, bgra
    top, bottom = max(used_rows[0] - margin, 0), min(used_rows[-1] + margin + 1, height)
    columns = [x for x in range(width) if any(rows[y][x * 4 : x * 4 + 3] != WHITE
                                             for y in range(top, bottom))]  # fmt: skip
    left, right = max(columns[0] - margin, 0), min(columns[-1] + margin + 1, width)
    out = b"".join(rows[y][left * 4 : right * 4] for y in range(top, bottom))
    return right - left, bottom - top, out


def encode_png(width: int, height: int, bgra: bytes) -> bytes:
    """An 8-bit RGB PNG from BGRA pixels."""
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        row = bgra[y * stride : (y + 1) * stride]
        rgb = bytearray(width * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = row[2::4], row[1::4], row[0::4]
        raw += b"\x00" + rgb  # filter type 0 for each row

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data)
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )


def _inked(row: bytes) -> bool:
    return any(row[i : i + 3] != WHITE for i in range(0, len(row), 4))
