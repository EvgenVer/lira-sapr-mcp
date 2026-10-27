import pytest

from lira_sapr_mcp.config import Settings, load_settings
from lira_sapr_mcp.errors import LiraInputError


def test_missing_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "none.toml") == Settings()


def test_file_overrides_defaults(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('lira_version = 2024\ncall_timeout_s = 5\nlog_file = "x.log"\n')
    s = load_settings(p)
    assert s.lira_version == 2024
    assert s.call_timeout_s == 5
    assert s.log_file.name == "x.log"


def test_unknown_keys_are_rejected(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("call_timeout = 5\n")
    with pytest.raises(LiraInputError, match="call_timeout"):
        load_settings(p)
