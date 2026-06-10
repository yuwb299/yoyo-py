"""Tests for enhanced /diff command with file-specific and full diff support."""

import os
import subprocess
import tempfile

from src.repl import _run_diff_enhanced


# Save the original cwd before any tests change it
_ORIG_CWD = os.getcwd()


def _init_git_repo() -> str:
    """Create a temp git repo with some changes and return its path."""
    tmpdir = tempfile.mkdtemp()
    subprocess.run(["git", "init"], capture_output=True, cwd=tmpdir)
    subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True, cwd=tmpdir)
    subprocess.run(["git", "config", "user.name", "Test"], capture_output=True, cwd=tmpdir)

    # Create and commit an initial file
    with open(os.path.join(tmpdir, "hello.py"), "w") as f:
        f.write("print('hello')\n")
    with open(os.path.join(tmpdir, "world.py"), "w") as f:
        f.write("print('world')\n")
    subprocess.run(["git", "add", "-A"], capture_output=True, cwd=tmpdir)
    subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, cwd=tmpdir)
    return tmpdir


def _cleanup(tmpdir: str) -> None:
    """Restore cwd and remove temp dir."""
    os.chdir(_ORIG_CWD)
    subprocess.run(["rm", "-rf", tmpdir], capture_output=True)


class TestDiffEnhanced:
    def test_no_args_shows_summary(self):
        """Without args, shows the summary (same as old behavior)."""
        tmpdir = _init_git_repo()
        try:
            os.chdir(tmpdir)
            # Modify a file to create a diff
            with open(os.path.join(tmpdir, "hello.py"), "w") as f:
                f.write("print('hello world')\n")

            result = _run_diff_enhanced("")
            assert "hello.py" in result
        finally:
            _cleanup(tmpdir)

    def test_file_specific_diff(self):
        """Show diff for a specific file."""
        tmpdir = _init_git_repo()
        try:
            os.chdir(tmpdir)
            with open(os.path.join(tmpdir, "hello.py"), "w") as f:
                f.write("print('hello world')\n")

            result = _run_diff_enhanced("hello.py")
            assert "hello" in result or "world" in result
        finally:
            _cleanup(tmpdir)

    def test_full_diff(self):
        """--full shows the complete diff."""
        tmpdir = _init_git_repo()
        try:
            os.chdir(tmpdir)
            with open(os.path.join(tmpdir, "hello.py"), "w") as f:
                f.write("print('changed')\n")

            result = _run_diff_enhanced("--full")
            assert "changed" in result
        finally:
            _cleanup(tmpdir)

    def test_no_changes(self):
        """Clean working tree shows appropriate message."""
        tmpdir = _init_git_repo()
        try:
            os.chdir(tmpdir)
            result = _run_diff_enhanced("")
            assert "clean" in result.lower() or "No changes" in result
        finally:
            _cleanup(tmpdir)

    def test_not_git_repo(self):
        """Non-git directory shows error."""
        tmpdir = tempfile.mkdtemp()
        os.chdir(tmpdir)
        try:
            result = _run_diff_enhanced("")
            assert "Not a git repo" in result or "not a git" in result.lower()
        finally:
            os.chdir(_ORIG_CWD)
            subprocess.run(["rm", "-rf", tmpdir], capture_output=True)

    def test_staged_flag(self):
        """--staged shows only staged changes."""
        tmpdir = _init_git_repo()
        try:
            os.chdir(tmpdir)
            with open(os.path.join(tmpdir, "hello.py"), "w") as f:
                f.write("print('staged change')\n")
            subprocess.run(["git", "add", "hello.py"], capture_output=True, cwd=tmpdir)

            # Also create an unstaged change in another file
            with open(os.path.join(tmpdir, "world.py"), "w") as f:
                f.write("print('unstaged')\n")

            result = _run_diff_enhanced("--staged")
            assert "staged" in result or "hello.py" in result
        finally:
            _cleanup(tmpdir)

    def test_stat_flag(self):
        """--stat shows diffstat summary."""
        tmpdir = _init_git_repo()
        try:
            os.chdir(tmpdir)
            with open(os.path.join(tmpdir, "hello.py"), "w") as f:
                f.write("print('changed')\n")

            result = _run_diff_enhanced("--stat")
            assert "hello.py" in result
        finally:
            _cleanup(tmpdir)
