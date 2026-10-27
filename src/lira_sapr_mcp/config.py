"""Server settings: defaults overridden by an optional TOML file.

The file is looked up at ``LIRA_MCP_CONFIG`` or ``%APPDATA%/lira-sapr-mcp/config.toml``.
"""

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from lira_sapr_mcp.errors import LiraInputError


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "lira-sapr-mcp"


@dataclass(frozen=True)
class Settings:
    # LIRA release year to use, e.g. 2024; None picks the newest supported installation.
    lira_version: int | None = None
    # Seconds to wait for one LIRA call before reporting that LIRA is not answering.
    call_timeout_s: float = 60.0
    # Seconds a single analysis may run before the wait gives up (the analysis continues).
    analysis_timeout_s: float = 3600.0
    # Folder next to a model where backups are written before the first change.
    backup_dir_name: str = "lira-mcp-backups"
    log_file: Path = app_data_dir() / "server.log"


def default_config_path() -> Path:
    env = os.environ.get("LIRA_MCP_CONFIG")
    return Path(env) if env else app_data_dir() / "config.toml"


def load_settings(path: Path | None = None) -> Settings:
    path = path or default_config_path()
    if not path.exists():
        return Settings()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    known = {f.name for f in fields(Settings)}
    unknown = set(raw) - known
    if unknown:
        raise LiraInputError(f"Unknown settings in {path}: {', '.join(sorted(unknown))}")
    if "log_file" in raw:
        raw["log_file"] = Path(raw["log_file"])
    return Settings(**raw)
