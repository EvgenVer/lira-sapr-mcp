"""Modal windows that LIRA shows, read and answered through Win32, not COM.

While LIRA waits for the user, calls into it may hang, so this module never uses COM and
may run on any thread. A dialog is a visible window of LIRA's process with the standard
dialog class, or any window owned by a LIRA window that the dialog disabled.
"""

import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from lira_sapr_mcp.errors import LiraInputError

DIALOG_CLASS = "#32770"
BUTTON_CLASS = "Button"
TEXT_CLASSES = ("Static", "Edit", "RichEdit20W", "RICHEDIT50W")


@dataclass
class Dialog:
    hwnd: int
    title: str
    text: list[str] = field(default_factory=list)
    buttons: list[str] = field(default_factory=list)

    def describe(self) -> str:
        text = " ".join(self.text)
        return f"'{self.title}': {text} (buttons: {', '.join(self.buttons) or 'none'})"


class Windows(Protocol):
    def top_level(self, exe_name: str) -> list[int]: ...
    def children(self, hwnd: int) -> list[int]: ...
    def class_name(self, hwnd: int) -> str: ...
    def text(self, hwnd: int) -> str: ...
    def owner(self, hwnd: int) -> int: ...
    def enabled(self, hwnd: int) -> bool: ...
    def click(self, hwnd: int) -> None: ...


class Win32Windows:
    """The real windows of this desktop."""

    def top_level(self, exe_name: str) -> list[int]:
        import win32gui
        import win32process

        found: list[int] = []
        names: dict[int, str] = {}

        def visit(hwnd: int, _: Any) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid not in names:
                names[pid] = _exe_name(pid)
            if names[pid] == exe_name.lower():
                found.append(hwnd)

        win32gui.EnumWindows(visit, None)
        return found

    def children(self, hwnd: int) -> list[int]:
        import win32gui

        found: list[int] = []

        def visit(child: int, _: Any) -> None:
            if win32gui.IsWindowVisible(child):
                found.append(child)

        # A window without children raises on some Windows versions.
        with contextlib.suppress(Exception):
            win32gui.EnumChildWindows(hwnd, visit, None)
        return found

    def class_name(self, hwnd: int) -> str:
        import win32gui

        return win32gui.GetClassName(hwnd)

    def text(self, hwnd: int) -> str:
        import win32gui

        return win32gui.GetWindowText(hwnd)

    def owner(self, hwnd: int) -> int:
        import win32con
        import win32gui

        return win32gui.GetWindow(hwnd, win32con.GW_OWNER)

    def enabled(self, hwnd: int) -> bool:
        import win32gui

        return bool(win32gui.IsWindowEnabled(hwnd))

    def click(self, hwnd: int) -> None:
        import win32api
        import win32con

        # Posted, not sent: the dialog's own message loop handles it, nothing waits here.
        win32api.PostMessage(hwnd, win32con.BM_CLICK, 0, 0)


def _exe_name(pid: int) -> str:
    import win32api
    import win32con
    import win32process

    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        return Path(win32process.GetModuleFileNameEx(handle, 0)).name.lower()
    except Exception:  # processes of other users or already gone
        return ""


def find_dialogs(exe: str, windows: Windows | None = None) -> list[Dialog]:
    """The dialogs LIRA (process of ``exe``) shows now."""
    w = windows or Win32Windows()
    tops = w.top_level(Path(exe).name)
    dialogs = []
    for hwnd in tops:
        owner = w.owner(hwnd)
        blocking = owner in tops and not w.enabled(owner)
        if w.class_name(hwnd) != DIALOG_CLASS and not blocking:
            continue
        dialog = Dialog(hwnd, w.text(hwnd).strip())
        for child in w.children(hwnd):
            kind, text = w.class_name(child), _clean(w.text(child))
            if not text:
                continue
            if kind == BUTTON_CLASS:
                dialog.buttons.append(text)
            elif kind in TEXT_CLASSES and len(dialog.text) < 20:
                dialog.text.append(text)
        dialogs.append(dialog)
    return dialogs


def press_button(
    exe: str, button: str, title: str | None = None, windows: Windows | None = None
) -> Dialog:
    """Click a button (by its text, case and '&' ignored) of LIRA's dialog: the only one
    shown, or the one whose title contains ``title``."""
    w = windows or Win32Windows()
    dialogs = find_dialogs(exe, w)
    if title:
        dialogs = [d for d in dialogs if title.casefold() in d.title.casefold()]
    if not dialogs:
        raise LiraInputError("LIRA shows no dialog" + (f" titled {title!r}" if title else ""))
    if len(dialogs) > 1:
        names = "; ".join(repr(d.title) for d in dialogs)
        raise LiraInputError(f"LIRA shows several dialogs ({names}): give the title")
    dialog = dialogs[0]
    wanted = _key(button)
    for child in w.children(dialog.hwnd):
        if w.class_name(child) == BUTTON_CLASS and _key(w.text(child)) == wanted:
            w.click(child)
            return dialog
    raise LiraInputError(f"Dialog {dialog.title!r} has no button {button!r}: {dialog.buttons}")


def _clean(text: str) -> str:
    return " ".join(text.replace("&", "").split())


def _key(text: str) -> str:
    return _clean(text).casefold()
