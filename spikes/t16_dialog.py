"""T16 probe: LIRA's About dialog (command 57664). Is COM blocked while it is open?
What do its windows look like, and does BM_CLICK on its button close it?
"""

import time

import win32api
import win32con
import win32gui
import win32process

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install
from lira_sapr_mcp.com.worker import ComWorker
from lira_sapr_mcp.errors import LiraTimeoutError

ABOUT = 57664


def exe_of(pid: int) -> str:
    try:
        h = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        return win32process.GetModuleFileNameEx(h, 0)
    except Exception:
        return ""


def lira_windows() -> list[dict]:
    found = []

    def top(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if "lirasapr" not in exe_of(pid).lower():
            return
        children = []

        def child(ch, _):
            if win32gui.IsWindowVisible(ch):
                children.append((ch, win32gui.GetClassName(ch), win32gui.GetWindowText(ch)))

        try:
            win32gui.EnumChildWindows(hwnd, child, None)
        except Exception:
            pass
        found.append({
            "hwnd": hwnd,
            "class": win32gui.GetClassName(hwnd),
            "title": win32gui.GetWindowText(hwnd),
            "owner": win32gui.GetWindow(hwnd, win32con.GW_OWNER),
            "enabled": win32gui.IsWindowEnabled(hwnd),
            "children": children,
        })

    win32gui.EnumWindows(top, None)
    return found


worker = ComWorker()
adapter = ComLiraAdapter(pick_install(find_installs(), None))
worker.call(adapter.connect, timeout=120)
try:
    print("before:", [(w["class"], w["title"], w["enabled"]) for w in lira_windows()])
    t0 = time.monotonic()
    worker.call(adapter._app.StartCmd, ABOUT, timeout=10)
    print(f"StartCmd returned after {time.monotonic() - t0:.1f} s")
    time.sleep(1.5)
    windows = lira_windows()
    for w in windows:
        print({k: v for k, v in w.items() if k != "children"})
        for c in w["children"][:15]:
            print("    ", c)
    try:
        n = worker.call(lambda: adapter._app.DocumentCount, timeout=5)
        print("COM answers while the dialog is open: DocumentCount =", n)
    except LiraTimeoutError as exc:
        print("COM blocked:", exc)
    dialog = next((w for w in windows if w["class"] == "#32770"), None)
    if dialog:
        button = next((c for c in dialog["children"] if c[1] == "Button"), None)
        print("pressing", button)
        win32api.PostMessage(button[0], win32con.BM_CLICK, 0, 0)
        time.sleep(1.0)
        print("after:", [(w["class"], w["title"], w["enabled"]) for w in lira_windows()])
        n = worker.call(lambda: adapter._app.DocumentCount, timeout=10)
        print("COM after closing: DocumentCount =", n)
finally:
    worker.call(adapter.disconnect, timeout=30)
    worker.stop()
