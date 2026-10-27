import subprocess
import sys

from lira_sapr_mcp import __version__


def test_version_is_set():
    assert __version__ == "0.1.0"


def test_cli_prints_version():
    out = subprocess.run(
        [sys.executable, "-m", "lira_sapr_mcp", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == f"lira-sapr-mcp {__version__}"
