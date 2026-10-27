"""Command-line entry point: ``lira-sapr-mcp`` runs the MCP server over stdio."""

import logging
import sys

from lira_sapr_mcp import __version__


def setup_logging(log_file) -> None:
    # stdout carries the MCP protocol in stdio mode, so the log goes to a file.
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def main() -> None:
    if "--version" in sys.argv[1:]:
        print(f"lira-sapr-mcp {__version__}")
        return
    from lira_sapr_mcp.config import load_settings
    from lira_sapr_mcp.server import build_server
    from lira_sapr_mcp.services.session import LiraSession

    settings = load_settings()
    setup_logging(settings.log_file)
    logging.getLogger(__name__).info("lira-sapr-mcp %s starting", __version__)
    build_server(LiraSession(settings)).run("stdio")


if __name__ == "__main__":
    main()
