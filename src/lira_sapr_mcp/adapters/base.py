"""Version-independent data shapes the adapters return."""

import os
import re
from dataclasses import dataclass, field

from lira_sapr_mcp.errors import LiraInputError

# LIRA "system label" (признак схемы): which degrees of freedom each node has.
MODEL_TYPES = {
    1: "2D truss/frame in XOZ: X, Z",
    2: "2D frame in XOZ: X, Z, UY",
    3: "grillage or plate in XOY: Z, UX, UY",
    4: "3D truss: X, Y, Z",
    5: "general 3D: X, Y, Z, UX, UY, UZ",
}

UNIT_NAMES = {
    "geometry": ["m", "cm", "mm", "ft", "in"],
    "force": ["g", "kg", "t", "N", "kN", "MN", "lb", "kips"],
    "stress": ["g", "kg", "t", "N", "kN", "MN", "lb", "kips", "Pa", "kPa", "MPa"],
    "temperature": ["C", "F"],
    "weight": ["g", "kg", "t", "lb", "kips"],
}


@dataclass(frozen=True)
class DocInfo:
    title: str
    path: str
    model_type: int
    modified: bool
    active: bool
    saved: bool = field(default=True)


@dataclass(frozen=True)
class TableError:
    row: int
    column: int
    message: str


@dataclass(frozen=True)
class Units:
    """Units LIRA uses in input tables right now (a LIRA-wide user setting)."""

    geometry: str
    sections: str
    loads: str
    loads_per: str
    materials: str
    materials_per: str
    displacements: str
    forces: str
    forces_per: str
    stresses: str
    stresses_per: str
    temperature: str


def parse_table_errors(text: str) -> list[TableError]:
    """Parse ``Apply()`` errors: one ``row\\tcolumn\\tmessage`` per line, 0-based indices."""
    errors = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        try:
            errors.append(TableError(int(parts[0]), int(parts[1]), parts[2].strip()))
        except (ValueError, IndexError):
            errors.append(TableError(-1, -1, line.strip()))
    return errors


def norm_path(path: str) -> str:
    """Comparable form of a file path (absolute, case-folded on Windows)."""
    return os.path.normcase(os.path.abspath(path)) if path else ""


def parse_numbers(numbers: list[int] | str | None) -> list[int] | None:
    """Accept [1, 2, 5] or LIRA-style "1-3 7 10-12" (commas allowed); None when empty."""
    if numbers is None or isinstance(numbers, list):
        return numbers or None
    out: list[int] = []
    for part in re.split(r"[,\s]+", str(numbers).strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if b < a or b - a > 1_000_000:
                raise LiraInputError(f"Bad range {part!r}")
            out.extend(range(a, b + 1))
        elif part.isdigit():
            out.append(int(part))
        else:
            raise LiraInputError(f"Bad number list {numbers!r}: use e.g. '1-3 7 10-12'")
    return out or None


def decode_lira_text(raw: bytes) -> str | None:
    """LIRA writes text files in UTF-8 (with BOM) or, in older paths, in cp1251."""
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def normalize_rows(data: object) -> list[list[object]]:
    """Turn the 2-D array LIRA returns into a list of rows with empty cells as ``None``."""
    if not data:
        return []
    rows = []
    for row in data:  # type: ignore[union-attr]
        rows.append([None if cell in ("", None) else cell for cell in row])
    return rows
