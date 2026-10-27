"""T2 spike, step 8: list LIRA menu commands (id and text) from Visor.resources.dll."""

import struct
import sys

import win32api
import win32con

path = sys.argv[1]
pat = sys.argv[2].lower() if len(sys.argv) > 2 else ""
h = win32api.LoadLibraryEx(path, 0, win32con.LOAD_LIBRARY_AS_DATAFILE)


def read_str(data, pos):
    end = pos
    while data[end : end + 2] != b"\0\0":
        end += 2
    return data[pos:end].decode("utf-16-le"), end + 2


def parse(data):
    ver, off = struct.unpack_from("<HH", data, 0)
    items = []
    if ver == 0:  # standard MENUITEMTEMPLATE
        pos = 4
        depth = 1
        while pos < len(data) and depth:
            (flags,) = struct.unpack_from("<H", data, pos)
            pos += 2
            if flags & 0x10:  # MF_POPUP
                text, pos = read_str(data, pos)
                items.append((None, text))
                depth += 1
            else:
                (cid,) = struct.unpack_from("<H", data, pos)
                pos += 2
                text, pos = read_str(data, pos)
                items.append((cid, text))
            if flags & 0x80:  # MF_END
                depth -= 1
    else:  # extended
        pos = 4 + off
        while pos + 14 <= len(data):
            typ, state, cid, res = struct.unpack_from("<IIIH", data, pos)
            pos += 14
            text, pos = read_str(data, pos)
            pos = (pos + 3) & ~3
            if res & 0x01:
                pos += 4
            items.append((cid, text))
    return items


out = []
for name in win32api.EnumResourceNames(h, win32con.RT_MENU):
    try:
        data = win32api.LoadResource(h, win32con.RT_MENU, name)
        for cid, text in parse(data):
            if pat in text.lower():
                out.append(f"{name}\t{cid}\t{text}")
    except Exception as e:
        out.append(f"{name}\tERROR {e}")
open(sys.argv[3], "w", encoding="utf-8").write("\n".join(out))
print(len(out))
