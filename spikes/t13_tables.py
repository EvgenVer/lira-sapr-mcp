"""T13 probe: column counts and sample rows of every input table in LIRA examples 01, 02, 04.

Copies the examples into spikes/out first; never touches the originals.
"""

import shutil
from collections import Counter
from pathlib import Path

from lira_sapr_mcp.adapters.com_adapter import ComLiraAdapter
from lira_sapr_mcp.adapters.discovery import find_installs, pick_install

MANUAL = Path(r"C:\Users\Public\Documents\LIRA SAPR\LIRA SAPR 2024\Manual\RU")
OUT = Path(__file__).parent / "out"
EXAMPLES = {
    "ex01": next((MANUAL / "01_плоская рама ЖБ").glob("*.lir")),
    "ex02": next((MANUAL / "02_плита ЖБ").glob("*.lir")),
    "ex04": next(
        (MANUAL / "04_пространственный каркас с фунд_плитой на упругом основании").glob("*.lir")
    ),
}

adapter = ComLiraAdapter(pick_install(find_installs(), None))
adapter.connect()
lines = []
try:
    for name, src in EXAMPLES.items():
        copy = OUT / f"t13_{name}.lir"
        shutil.copy(src, copy)
        info, _ = adapter.open_document(str(copy))
        lines.append(f"##### {name} {src.name}")
        for table in sorted(adapter.table_kinds):
            try:
                rows = adapter.read_table(str(copy), table)
            except Exception as exc:
                lines.append(f"== {table}: error {exc}")
                continue
            widths = Counter(len(r) for r in rows)
            lines.append(f"== {table}: {len(rows)} rows, widths {dict(widths)}")
            if table == "Elements_TypeAndNodes":
                types = Counter(r[1] for r in rows)
                lines.append(f"   FE types: {dict(types)}")
            for r in rows[:3]:
                lines.append("   " + " | ".join("" if c is None else str(c) for c in r))
        adapter.close_document(info.path, True)
finally:
    adapter.disconnect()
(OUT / "t13_tables.txt").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
