"""Command-line entry point. The MCP server itself arrives in task T5."""

import sys

from lira_sapr_mcp import __version__


def main() -> None:
    if "--version" in sys.argv[1:]:
        print(f"lira-sapr-mcp {__version__}")
        return
    print("lira-sapr-mcp: the MCP server is not implemented yet", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
