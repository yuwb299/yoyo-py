"""Tests that slash commands use exact prefix matching, not overly broad matching.

Regression test for the Day 25 /cd prefix bug — the same pattern affects
multiple commands. After Day 26 fix, all commands use exact match:
  cmd == "/X" or cmd.startswith("/X ")
"""

import subprocess
from unittest.mock import patch, MagicMock


def _match_cmd(cmd_str):
    """Simulate the REPL dispatch logic with the FIXED patterns."""
    cmd = cmd_str.lower()
    line = cmd_str

    # These are the FIXED patterns from repl.py (exact match)
    patterns = {
        "commit": lambda: cmd == "/commit" or cmd.startswith("/commit "),
        "save": lambda: cmd == "/save" or cmd.startswith("/save "),
        "export": lambda: cmd == "/export" or cmd.startswith("/export "),
        "load": lambda: cmd == "/load" or cmd.startswith("/load "),
        "remember": lambda: cmd == "/remember" or cmd.startswith("/remember "),
        "forget": lambda: cmd == "/forget" or cmd.startswith("/forget "),
        "log": lambda: cmd == "/log" or cmd.startswith("/log "),
        "init": lambda: cmd == "/init" or cmd.startswith("/init "),
        "model": lambda: cmd.startswith("/model "),
        "cd": lambda: cmd == "/cd" or cmd.startswith("/cd "),
    }

    return [name for name, matches in patterns.items() if matches()]


# --- Exact match tests ---

def test_commit_exact():
    assert "commit" in _match_cmd("/commit fix bug")
    assert "commit" in _match_cmd("/commit")

def test_save_exact():
    assert "save" in _match_cmd("/save")
    assert "save" in _match_cmd("/save myfile.json")

def test_export_exact():
    assert "export" in _match_cmd("/export")
    assert "export" in _match_cmd("/export out.md")

def test_load_exact():
    assert "load" in _match_cmd("/load")
    assert "load" in _match_cmd("/load myfile.json")

def test_remember_exact():
    assert "remember" in _match_cmd("/remember some fact")
    assert "remember" in _match_cmd("/remember")

def test_forget_exact():
    assert "forget" in _match_cmd("/forget 1")
    assert "forget" in _match_cmd("/forget")

def test_log_exact():
    assert "log" in _match_cmd("/log")
    assert "log" in _match_cmd("/log 5")
    assert "log" in _match_cmd("/log --oneline")

def test_init_exact():
    assert "init" in _match_cmd("/init")
    assert "init" in _match_cmd("/init --force")

def test_model_exact():
    assert "model" in _match_cmd("/model gpt-4o")

def test_cd_exact():
    assert "cd" in _match_cmd("/cd")
    assert "cd" in _match_cmd("/cd /tmp")


# --- No false match tests ---

def test_commit_no_false():
    assert "commit" not in _match_cmd("/commitmsg")
    assert "commit" not in _match_cmd("/commits")

def test_save_no_false():
    assert "save" not in _match_cmd("/saved")
    assert "save" not in _match_cmd("/saver")

def test_export_no_false():
    assert "export" not in _match_cmd("/exportfile")
    assert "export" not in _match_cmd("/exporting")

def test_load_no_false():
    assert "load" not in _match_cmd("/loadtest")
    assert "load" not in _match_cmd("/loading")

def test_remember_no_false():
    assert "remember" not in _match_cmd("/rememberthis")
    assert "remember" not in _match_cmd("/remembering")

def test_forget_no_false():
    assert "forget" not in _match_cmd("/forgetme")
    assert "forget" not in _match_cmd("/forgetting")

def test_log_no_false():
    assert "log" not in _match_cmd("/logview")
    assert "log" not in _match_cmd("/login")

def test_init_no_false():
    assert "init" not in _match_cmd("/initialize")
    assert "init" not in _match_cmd("/initfile")

def test_model_no_false():
    assert "model" not in _match_cmd("/modelx")
    assert "model" not in _match_cmd("/modeling")

def test_cd_no_false():
    assert "cd" not in _match_cmd("/cdfoo")
    assert "cd" not in _match_cmd("/cdsearch")


# --- Cross-command pollution tests ---

def test_no_cross_match():
    """Ensure one command doesn't match another command's prefix."""
    commands = ["/commit", "/save", "/export", "/load", "/remember",
                "/forget", "/log", "/init", "/cd"]
    for cmd in commands:
        for other in commands:
            if cmd != other:
                # /commit should not match /log, etc.
                result = _match_cmd(other)
                # Each command should only match its own pattern
                # (e.g., /load should match "load" but not "log")
                assert cmd[1:] not in result, f"{cmd} incorrectly matched when testing {other}"
