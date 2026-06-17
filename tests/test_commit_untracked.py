"""Tests: /commit must commit untracked files, not silently report "no changes".

Before this fix, _git_commit detected "no changes" by checking only
  git diff --name-status        (unstaged tracked changes)
  git diff --cached --name-status (staged changes)
Neither shows UNTRACKED files. So if the only change in the repo was a newly
created file, /commit returned "[No changes to commit]" and the file was
never committed — a silent data-omission bug. The fix uses `git status --porcelain`
which DOES include untracked files (`??`).
"""

import os
import subprocess

import pytest

from src.repl import _git_commit


def _git(repo, *args):
    """Run a git command in repo, return CompletedProcess."""
    return subprocess.run(
        ["git", *args], cwd=str(repo),
        capture_output=True, text=True,
    )


@pytest.fixture
def git_repo(tmp_path):
    """Create a real git repo with one initial commit (clean tree)."""
    r = tmp_path / "repo"
    r.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    # init via subprocess with explicit env (git config --local also works)
    subprocess.run(["git", "init"], cwd=str(r), check=True,
                   capture_output=True, env=env)
    (r / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "add", "-A"], cwd=str(r), check=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(r),
                   check=True, capture_output=True, env=env)
    # Run _git_commit from inside the repo so it operates on this repo
    old_cwd = os.getcwd()
    os.chdir(str(r))
    try:
        yield r
    finally:
        os.chdir(old_cwd)


def test_untracked_only_file_is_committed(git_repo):
    """A lone untracked file must be committed, not reported as 'no changes'."""
    (git_repo / "new_file.txt").write_text("hello\n")

    result = _git_commit("add new file")

    assert "[No changes to commit]" not in result, (
        f"untracked file was silently skipped: {result!r}"
    )
    assert "[ERROR]" not in result, f"commit failed: {result!r}"
    # Verify the file is actually committed (clean working tree)
    status = _git(git_repo, "status", "--porcelain")
    assert status.stdout.strip() == "", (
        f"working tree not clean after commit: {status.stdout!r}"
    )
    # And the file is tracked
    log = _git(git_repo, "log", "--oneline")
    assert "add new file" in log.stdout


def test_tracked_modification_still_committed(git_repo):
    """Regression guard: normal tracked-file edits still commit."""
    (git_repo / "seed.txt").write_text("changed\n")
    result = _git_commit("edit seed")
    assert "[No changes to commit]" not in result
    assert "[ERROR]" not in result


def test_clean_repo_reports_no_changes(git_repo):
    """Regression guard: truly clean repo still reports no changes."""
    result = _git_commit("nothing")
    assert "[No changes to commit]" in result
