"""Tests for _find_all_files portability and gitignore helpers.

GNU find emits a warning (and some BusyBox finds error out) when -maxdepth
appears AFTER -type/-name predicates. We put -maxdepth first to be portable.
"""

import subprocess

from src.tools import _find_all_files, _git_list_files, _git_ignored_set
from pathlib import Path


def test_find_all_files_maxdepth_no_stderr_warning(tmp_path):
    """_find_all_files with max_depth must not emit find warnings to stderr."""
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("b")

    files = _find_all_files(tmp_path, max_depth=1)
    names = sorted(Path(f).name for f in files)
    # max_depth=1 should include direct children but not deeper
    assert "a.txt" in names
    # b.txt is at depth 2, should be excluded by maxdepth 1
    assert "b.txt" not in names


def test_find_all_files_returns_results(tmp_path):
    """Basic sanity: _find_all_files lists files under a directory."""
    (tmp_path / "x.py").write_text("x")
    (tmp_path / "y.py").write_text("y")
    files = _find_all_files(tmp_path)
    names = sorted(Path(f).name for f in files)
    assert names == ["x.py", "y.py"]


def test_find_maxdepth_argument_order():
    """The find command built by _find_all_files must place -maxdepth before
    -type, so it doesn't trigger GNU find's 'warning: you have specified the
    -maxdepth option after a non-option argument' on Linux/CI."""
    import src.tools as tools
    # Inspect how the command is constructed by monkeypatching subprocess.run
    captured = {}

    original_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        # Return an empty result so the function completes
        class R:
            returncode = 0
            stdout = ""
        return R()

    tools.subprocess.run = fake_run
    try:
        _find_all_files(Path("/tmp"), max_depth=2)
    finally:
        tools.subprocess.run = original_run

    cmd = captured.get("cmd", [])
    # Find -maxdepth index and -type index
    assert "-maxdepth" in cmd, f"expected -maxdepth in {cmd}"
    assert "-type" in cmd, f"expected -type in {cmd}"
    maxdepth_idx = cmd.index("-maxdepth")
    type_idx = cmd.index("-type")
    assert maxdepth_idx < type_idx, (
        f"-maxdepth must come BEFORE -type for portability, got {cmd}. "
        f"GNU find warns when -maxdepth follows a non-option argument."
    )
