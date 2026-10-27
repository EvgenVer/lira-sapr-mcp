"""T2 spike: list visible top-level windows of LiraSapr.exe with their child controls."""

import ctypes

import win32api
import win32con
import win32gui
import win32process

out = open("spikes/out/t2_windows.log", "w", encoding="utf-8")


def exe_of(pid):
    try:
        h = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        return win32process.GetModuleFileNameEx(h, 0)
    except Exception:
        buf = ctypes.create_unicode_buffer(1024)
        return ""


def top(hwnd, _):
    if not win32gui.IsWindowVisible(hwnd):
        return
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    exe = exe_of(pid)
    if "lirasapr" not in exe.lower():
        return
    print(
        f"TOP {hwnd} class={win32gui.GetClassName(hwnd)!r} title={win32gui.GetWindowText(hwnd)!r} "
        f"owner={win32gui.GetWindow(hwnd, win32con.GW_OWNER)} enabled={win32gui.IsWindowEnabled(hwnd)}",
        file=out,
    )

    def child(ch, _):
        if win32gui.IsWindowVisible(ch):
            print(
                f"    child {ch} class={win32gui.GetClassName(ch)!r} text={win32gui.GetWindowText(ch)!r}",
                file=out,
            )

    try:
        win32gui.EnumChildWindows(hwnd, child, None)
    except Exception:
        pass


win32gui.EnumWindows(top, None)
