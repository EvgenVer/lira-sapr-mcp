"""LIRA's dialogs: found among its windows, answered by button, reported on time-outs."""

import time

import pytest
from mcp import Client

from fakes import fake_session
from lira_sapr_mcp.adapters.dialogs import Dialog, find_dialogs, press_button
from lira_sapr_mcp.errors import LiraInputError, LiraTimeoutError
from lira_sapr_mcp.server import build_server

MAIN, ABOUT, PALETTE, OTHER = 1, 2, 3, 4


class FakeWindows:
    """LIRA's main window (disabled by a modal About box) and a tool palette."""

    def __init__(self, main_enabled=False):
        self.windows = {
            MAIN: ("Afx:main", "ЛИРА-САПР 2024", 0, main_enabled, []),
            ABOUT: ("#32770", "О программе", MAIN, True, [10, 11, 12, 13]),
            PALETTE: ("Afx:palette", "Палитра", MAIN, True, [20]),
        }
        self.controls = {
            10: ("Static", "ЛИРА-САПР 2024 R2.3"),
            11: ("Static", ""),
            12: ("Button", "&OK"),
            13: ("Button", "Отмена"),
            20: ("Button", "Кнопка палитры"),
        }
        self.clicked = []

    def top_level(self, exe_name):
        assert exe_name == "LiraSapr.exe"
        return [MAIN, ABOUT, PALETTE]

    def children(self, hwnd):
        return self.windows[hwnd][4]

    def class_name(self, hwnd):
        return self.windows[hwnd][0] if hwnd in self.windows else self.controls[hwnd][0]

    def text(self, hwnd):
        return self.windows[hwnd][1] if hwnd in self.windows else self.controls[hwnd][1]

    def owner(self, hwnd):
        return self.windows[hwnd][2]

    def enabled(self, hwnd):
        return self.windows[hwnd][3]

    def click(self, hwnd):
        self.clicked.append(hwnd)


EXE = r"C:\LIRA\LiraSapr.exe"


def test_dialogs_are_dialog_windows_and_windows_that_block_lira():
    found = find_dialogs(EXE, FakeWindows())
    # The palette is owned by the disabled main window, so it blocks LIRA too.
    assert [d.title for d in found] == ["О программе", "Палитра"]
    about = found[0]
    assert about.text == ["ЛИРА-САПР 2024 R2.3"] and about.buttons == ["OK", "Отмена"]
    assert "buttons: OK, Отмена" in about.describe()


def test_a_free_palette_is_not_a_dialog():
    assert [d.title for d in find_dialogs(EXE, FakeWindows(main_enabled=True))] == ["О программе"]


def test_press_finds_the_button_by_text():
    w = FakeWindows(main_enabled=True)
    pressed = press_button(EXE, "ok", windows=w)
    assert pressed.title == "О программе" and w.clicked == [12]


def test_press_needs_one_dialog_and_a_real_button():
    with pytest.raises(LiraInputError, match="several dialogs"):
        press_button(EXE, "OK", windows=FakeWindows())
    with pytest.raises(LiraInputError, match="no button 'Да'"):
        press_button(EXE, "Да", title="программе", windows=FakeWindows())
    with pytest.raises(LiraInputError, match="no dialog titled 'Ошибка'"):
        press_button(EXE, "OK", title="Ошибка", windows=FakeWindows())


@pytest.mark.anyio
async def test_a_time_out_names_the_dialog_lira_waits_in(tmp_path):
    session, adapter = fake_session(tmp_path)
    adapter.dialogs_shown.append(Dialog(5, "Внимание", ["Сохранить изменения?"], ["Да", "Нет"]))
    with pytest.raises(LiraTimeoutError, match="'Внимание': Сохранить изменения"):
        await session.run(time.sleep, 1.0, timeout=0.2)
    adapter.dialogs_shown.clear()
    with pytest.raises(LiraTimeoutError) as plain:
        await session.run(time.sleep, 1.0, timeout=0.2)
    assert "shows a dialog" not in str(plain.value)
    session.close()


@pytest.mark.anyio
async def test_dialog_tools_list_and_press(tmp_path):
    session, adapter = fake_session(tmp_path)
    adapter.dialogs_shown.append(Dialog(5, "Внимание", ["Сохранить?"], ["Да", "Нет"]))
    async with Client(build_server(session)) as client:
        listed = await client.call_tool("lira_dialogs", {})
        pressed = await client.call_tool("lira_press_dialog_button", {"button": "Нет"})
        none = await client.call_tool("lira_press_dialog_button", {"button": "Нет"})
    assert listed.structured_content["dialogs"][0]["buttons"] == ["Да", "Нет"]
    assert pressed.structured_content["pressed"] == {"title": "Внимание", "button": "Нет"}
    assert pressed.structured_content["dialogs"] == []
    assert none.is_error
