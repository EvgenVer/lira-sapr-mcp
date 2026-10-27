"""Copies of model files made before the server changes or overwrites them."""

import logging
import shutil
from datetime import datetime
from pathlib import Path

from lira_sapr_mcp.errors import LiraInputError

log = logging.getLogger(__name__)


class Backups:
    """Back up each model file once per server session, before its first change."""

    def __init__(self, dir_name: str) -> None:
        self.dir_name = dir_name
        self._done: dict[str, Path] = {}

    def ensure(self, model_path: str) -> Path | None:
        """Copy ``model_path`` into the backup folder next to it, unless done already.

        Returns the backup path, or None when there is no file on disk yet.
        """
        src = Path(model_path)
        key = str(src.resolve()).lower()
        if key in self._done:
            return self._done[key]
        if src.suffix.lower() != ".lir" or not src.is_file():
            return None
        folder = src.parent / self.dir_name
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dst = folder / f"{src.stem}_{stamp}.lir"
        try:
            folder.mkdir(exist_ok=True)
            shutil.copy2(src, dst)
        except OSError as exc:
            raise LiraInputError(
                f"Could not back up {src} to {folder}: {exc}. Nothing was changed."
            ) from exc
        self._done[key] = dst
        log.info("backup of %s written to %s", src, dst)
        return dst
