"""Built-in tools — the agent's hands for interacting with the world.

Each tool is:
1. A Python function that does the work
2. An OpenAI-format function schema for the LLM to understand

Tools: bash, read_file, write_file, edit_file, search, list_files, mkdir, glob, copy_file, rename
"""

from __future__ import annotations

import os
import subprocess
import re
from pathlib import Path
from typing import Any


# ─── Tool implementations ────────────────────────────────────────────

def tool_bash(command: str, timeout: int = 120, workdir: str | None = None) -> str:
    """Run a shell command and return stdout + stderr.

    Args:
        command: Shell command to execute.
        timeout: Max seconds to wait (default 120, max 600).
        workdir: Working directory (default: current).

    Returns:
        Combined stdout + stderr, truncated to 50KB.
    """
    # Clamp timeout to reasonable range — LLM could send absurd values
    timeout = max(1, min(timeout, 600))
    # Reject empty/whitespace commands up front. Without this, subprocess.run("")
    # succeeds with empty output, and the LLM can't tell whether the command
    # ran with no output or was never valid — leading to confused retries.
    if not command or not str(command).strip():
        return "[ERROR] Empty command — nothing to run"
    # Resolve workdir up front. If workdir is invalid, subprocess.run raises
    # FileNotFoundError ([Errno 2]) or NotADirectoryError ([Errno 20]) with
    # cryptic messages that the LLM can't interpret. Translate to clear
    # messages naming the bad path so the caller knows what to fix.
    cwd = workdir or os.getcwd()
    if workdir:
        wd_path = Path(workdir)
        if not wd_path.exists():
            return f"[ERROR] Working directory does not exist: {workdir}"
        if not wd_path.is_dir():
            return f"[ERROR] Working directory is not a directory (it is a file): {workdir}"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n--- stderr ---\n" + result.stderr) if output else result.stderr

        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"

        return _truncate(output, 50000)

    except subprocess.TimeoutExpired as e:
        # Capture partial output from the timeout exception — the process
        # may have produced useful stdout/stderr before hitting the limit.
        # e.output and e.stderr are bytes (or None) from subprocess.
        parts = [f"[TIMEOUT] Command timed out after {timeout}s"]
        if e.output:
            try:
                partial = e.output.decode("utf-8", errors="replace")
            except AttributeError:
                partial = str(e.output)
            if partial.strip():
                parts.append(f"\n--- partial stdout ---\n{partial}")
        if e.stderr:
            try:
                partial_err = e.stderr.decode("utf-8", errors="replace")
            except AttributeError:
                partial_err = str(e.stderr)
            if partial_err.strip():
                parts.append(f"\n--- partial stderr ---\n{partial_err}")
        return _truncate("\n".join(parts), 50000)
    except Exception as e:
        return f"[ERROR] {e}"


def tool_read_file(path: str, offset: int = 1, limit: int = 500) -> str:
    """Read a text file with line numbers.

    Args:
        path: File path to read.
        offset: Starting line number (1-indexed, default 1).
        limit: Max lines to read (default 500, max 2000).

    Returns:
        File content with line numbers, or error message.
    """
    limit = min(limit, 2000)
    # Clamp limit to >=1. A non-positive limit produced nonsensical output:
    # limit=0 → "[Showing lines 1-0 of N]" (empty range), and limit=-3 →
    # "[Showing lines 1--3 of N]" (double-minus, broken formatting).
    # Treat any non-positive value as "use the default 500".
    if limit < 1:
        limit = 500
    # Clamp offset to >=1. offset=0 or negative would compute start = max(0, offset-1)
    # which silently reads from the start — that's actually fine behavior, but
    # we make it explicit so the header line numbers stay sensible.
    if offset < 1:
        offset = 1
    try:
        p = Path(path)
        if not p.exists():
            return f"[ERROR] File not found: {path}"
        if not p.is_file():
            return f"[ERROR] Not a file: {path}"
        if _is_binary(p):
            return f"[ERROR] Binary file, cannot read: {path}"

        # For large files, use incremental reading to avoid loading the
        # entire file into memory. Only read the lines we need.
        file_size = p.stat().st_size
        # Heuristic: if the file is >500KB and we're reading a small range,
        # use incremental reading. Otherwise, read the whole thing (simpler
        # and needed to get accurate total line count for the header).
        # We also need the total line count for the header, so for the tail
        # case we still have to count all lines — but we can do that without
        # storing all lines in memory.
        if file_size > 512000 and limit < 200:
            return _read_file_incremental(p, offset, limit, path)

        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)

        # 1-indexed offset
        start = max(0, offset - 1)

        # Offset past end of file — return clear message (matches the
        # incremental-path behavior for consistency)
        if start >= total:
            return f"[File: {path} ({total} lines)]\n[ERROR] Offset {offset} is past end of file"

        end = min(total, start + limit)

        selected = lines[start:end]
        # enumerate(start=start+1) already gives 1-indexed line numbers,
        # so we use i directly — adding +1 here caused off-by-one numbering.
        numbered = [f"{i:>6}|{line}" for i, line in enumerate(selected, start=start + 1)]

        header = f"[File: {path} ({total} lines)]\n"
        if start > 0 or end < total:
            header += f"[Showing lines {start + 1}-{end} of {total}]\n"

        return header + "\n".join(numbered)

    except Exception as e:
        return f"[ERROR] {e}"


def _read_file_incremental(p: Path, offset: int, limit: int, path_str: str) -> str:
    """Read a range of lines from a large file without loading it all.

    Used by tool_read_file for large files (>500KB) when reading a small range.
    Counts total lines by iterating (no storage), then reads the needed range.
    """
    # First pass: count total lines (no storage)
    total = 0
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for _ in fh:
            total += 1

    # Clamp offset
    start = max(0, offset - 1)
    end = min(total, start + limit)

    if start >= total:
        return f"[File: {path_str} ({total} lines)]\n[ERROR] Offset {offset} is past end of file"

    # Second pass: read only the needed lines
    selected = []
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for i, line_text in enumerate(fh):
            if i >= end:
                break
            if i >= start:
                selected.append(line_text.rstrip("\n"))

    numbered = [f"{i:>6}|{line}" for i, line in enumerate(selected, start=start + 1)]

    header = f"[File: {path_str} ({total} lines)]\n"
    if start > 0 or end < total:
        header += f"[Showing lines {start + 1}-{end} of {total}]\n"

    return header + "\n".join(numbered)


def tool_write_file(path: str, content: str) -> str:
    """Create or overwrite a file with the given content.

    Args:
        path: File path to write.
        content: Full content to write.

    Returns:
        Confirmation message with line count.
    """
    try:
        p = Path(path)
        # Back up existing file before overwriting — safety net for LLM mistakes
        _backup_file(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        line_count = 0 if content == "" else (content.count("\n") + (0 if content.endswith("\n") else 1))
        return f"[OK] Wrote {line_count} lines to {path}"
    except Exception as e:
        return f"[ERROR] {e}"


def tool_mkdir(path: str, parents: bool = True) -> str:
    """Create a directory.

    Args:
        path: Directory path to create.
        parents: If True, create parent directories as needed (default True).

    Returns:
        Confirmation or error message.
    """
    try:
        p = Path(path)
        if p.exists():
            if p.is_dir():
                return f"[OK] Directory already exists: {path}"
            return f"[ERROR] Path exists but is not a directory: {path}"
        if parents:
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.mkdir()
        return f"[OK] Created directory: {path}"
    except FileExistsError:
        return f"[ERROR] Directory already exists: {path}"
    except FileNotFoundError:
        return f"[ERROR] Parent directory does not exist. Use parents=True to create nested dirs."
    except Exception as e:
        return f"[ERROR] {e}"


def tool_copy_file(source: str, destination: str) -> str:
    """Copy a file to a new location.

    Args:
        source: Source file path.
        destination: Destination file path. Can be a directory (copies into it
            with the same filename). Refuses to overwrite existing files.

    Returns:
        Confirmation or error message.
    """
    try:
        import shutil
        src = Path(source)
        dst = Path(destination)

        if not src.exists():
            return f"[ERROR] Source not found: {source}"
        if not src.is_file():
            return f"[ERROR] Source is not a file: {source}"

        # If destination is an existing directory, copy into it with same filename
        if dst.is_dir():
            dst = dst / src.name

        if dst.exists():
            return f"[ERROR] Destination already exists: {destination}"

        # Create parent directories if needed
        dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(str(src), str(dst))
        return f"[OK] Copied {source} → {dst}"

    except Exception as e:
        return f"[ERROR] {e}"


def tool_edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Surgical text replacement in a file.

    Finds `old_string` and replaces it with `new_string`. By default,
    old_string must be unique in the file. Use replace_all=True to replace
    all occurrences.

    Args:
        path: File path to edit.
        old_string: Text to find (must be unique unless replace_all).
        new_string: Replacement text (use empty string to delete).
        replace_all: Replace all occurrences instead of requiring uniqueness.

    Returns:
        Diff-style preview of the change.
    """
    try:
        p = Path(path)
        if not p.exists():
            return f"[ERROR] File not found: {path}"

        # Reject empty old_string — it matches between every character in
        # str.replace(), which silently corrupts files
        if not old_string:
            return "[ERROR] old_string cannot be empty — use write_file to replace entire file contents"

        content = p.read_text(encoding="utf-8")
        count = content.count(old_string)

        if count == 0:
            return f"[ERROR] old_string not found in {path}"
        if count > 1 and not replace_all:
            return f"[ERROR] old_string found {count} times in {path}. Use replace_all=True or make old_string more specific."

        # Back up before modifying — safety net for LLM mistakes
        _backup_file(p)

        new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
        p.write_text(new_content, encoding="utf-8")

        # Build a simple diff preview
        old_lines = old_string.splitlines()
        new_lines = new_string.splitlines()
        diff = []
        for line in old_lines[:5]:
            diff.append(f"  - {line}")
        if len(old_lines) > 5:
            diff.append(f"  - ... ({len(old_lines) - 5} more lines)")
        for line in new_lines[:5]:
            diff.append(f"  + {line}")
        if len(new_lines) > 5:
            diff.append(f"  + ... ({len(new_lines) - 5} more lines)")

        action = f"Replaced {count} occurrence(s)" if replace_all else "Replaced 1 occurrence"
        return f"[OK] {action} in {path}\n" + "\n".join(diff)

    except Exception as e:
        return f"[ERROR] {e}"


def tool_search(
    pattern: str,
    path: str = ".",
    file_glob: str | None = None,
    max_results: int = 50,
    context: int = 0,
) -> str:
    """Search file contents with regex pattern. Returns matching lines with file paths and line numbers.

    Args:
        pattern: Regex pattern to search for.
        path: Directory to search in (default: current).
        file_glob: Optional file filter (e.g. '*.py').
        max_results: Max results to return (default 50).
        context: Number of context lines before and after each match (default 0, like grep -C).

    Returns:
        Matching lines with file paths and line numbers.
    """
    # Clamp context to non-negative
    context = max(context, 0)
    # Clamp max_results to >=1. Negative values crash rg ("value is not a
    # valid number"); 0 means "unlimited" in rg but the original code reported
    # "[No matches found]" on the empty output — both are misleading.
    max_results = max(1, max_results)

    # Reject empty/whitespace-only patterns up front. rg treats '' as a
    # match-all regex, which dumps EVERY line of EVERY file into the output —
    # wasting thousands of context tokens and never matching caller intent.
    # An empty search term is almost always a bug in the calling code.
    if not pattern or not str(pattern).strip():
        return "[ERROR] Search pattern is empty — provide a pattern to search for"

    # Validate the search path up front. Ripgrep returns exit code 2 with an
    # opaque "IO error ... os error 2" message for missing paths, which the
    # LLM can't interpret. A clear not-found message is far more actionable.
    if path:
        search_path = Path(path)
        if not search_path.exists():
            return f"[ERROR] Search path not found: {path}"

    try:
        # Build ripgrep command.
        # --max-count N is PER-FILE in rg, not total. We use it as a
        # performance cap (bounded above by max_results so a single huge
        # file can't blow up output), then enforce the REAL total cap in
        # Python below. Without the Python-side cap, max_results=2 across
        # 10 files returns up to 20 lines — silently misleading the LLM.
        per_file_cap = max(1, max_results)
        cmd = ["rg", "--line-number", "--max-count", str(per_file_cap)]
        if context > 0:
            cmd.extend(["--context", str(context)])
        if file_glob:
            cmd.extend(["--glob", file_glob])
        cmd.extend([pattern, path])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 1:
            return "[No matches found]"
        if result.returncode >= 2:
            # rc=2 could be invalid regex OR permission errors
            # Check stderr for regex-specific error
            if "regex" in result.stderr.lower() or "pattern" in result.stderr.lower():
                return f"[ERROR] Invalid regex pattern: {pattern}"
            # Permission errors or other issues — return what we have
            output = result.stdout.strip()
            if output:
                return _truncate(output, 50000)
            return f"[WARN] Search encountered issues: {result.stderr[:200]}"

        return _apply_total_match_cap(result.stdout, max_results)

    except FileNotFoundError:
        # Fallback to grep if rg not installed.
        # grep has no --max-count, so we always enforce the cap in Python.
        cmd = ["grep", "-rn", "-E"]
        if context > 0:
            cmd.extend([f"-C{context}"])
        cmd.append(pattern)
        if file_glob:
            cmd.extend(["--include", file_glob])
        cmd.extend([path])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return "[No matches found]"
            return _apply_total_match_cap(result.stdout, max_results)
        except Exception as e:
            return f"[ERROR] {e}"
    except subprocess.TimeoutExpired:
        return "[TIMEOUT] Search timed out"
    except Exception as e:
        return f"[ERROR] {e}"


def _apply_total_match_cap(raw_output: str, max_results: int) -> str:
    """Enforce a total cap on the number of match lines returned.

    rg's --max-count caps per-file matches, not the total. This helper takes
    raw rg/grep output and trims it to at most `max_results` match lines,
    appending a truncation notice so the LLM knows more matches exist and
    can re-search with a higher cap or a more specific pattern if needed.

    Match lines are lines produced by `rg --line-number` (format:
    `path:linenum:content` or `path-linenum-content` for context). We count
    a "match" as any line whose separator is `:` (the actual hit), since
    context lines use `-`. For grep -n output the format is the same.
    """
    if not raw_output:
        return ""

    lines = raw_output.rstrip("\n").splitlines()
    if not lines:
        return ""

    # Identify match lines vs context/separator lines.
    # Match line format:  path:NUM:content  (rg) or path:content (grep)
    # Context line format: path-NUM-content (rg only, with --context)
    # We can't perfectly distinguish without parsing, but we can cap on the
    # TOTAL line count which is a safe upper bound on match lines and matches
    # user intent (they asked for at most N results).
    total = len(lines)
    if total <= max_results:
        return _truncate(raw_output.strip(), 50000)

    kept = lines[:max_results]
    omitted = total - max_results
    body = "\n".join(kept)
    # Mention the cap value and how many lines were dropped, so the LLM/user
    # can decide whether to narrow the pattern or raise max_results.
    notice = f"\n... [{omitted} more match(es) omitted — raise max_results (currently {max_results}) or narrow the pattern to see them]"
    return _truncate(body + notice, 50000)


def tool_list_files(path: str = ".", glob_pattern: str | None = None, max_depth: int | None = None) -> str:
    """List files in a directory.

    When inside a git repo, respects .gitignore (excludes __pycache__, build
    artifacts, node_modules, etc). Outside git repos, lists all files.

    Args:
        path: Directory to list (default: current).
        glob_pattern: Filter by glob pattern (e.g. '*.py').
        max_depth: Maximum directory depth (None = unlimited).

    Returns:
        Sorted file listing with sizes.
    """
    try:
        # Clamp max_depth: treat <=0 (or None) as 'no limit'. Negative values
        # break find ('-maxdepth: value must be positive') and the os.walk
        # fallback's depth>=max_depth check is always true for negatives,
        # producing an empty result that gets mislabeled "[Empty directory]".
        if max_depth is not None and max_depth <= 0:
            max_depth = None

        p = Path(path)
        if not p.exists():
            return f"[ERROR] Path not found: {path}"
        if not p.is_dir():
            return f"[ERROR] Not a directory: {path}"

        # Try git-aware listing first: uses .gitignore to filter out noise
        # like __pycache__, node_modules, build artifacts, etc.
        # This saves LLM context tokens on irrelevant files.
        git_files = _git_list_files(p, max_depth=max_depth)
        if git_files is not None:
            files = git_files
        else:
            # Not a git repo — fall back to listing everything
            files = _find_all_files(p, max_depth=max_depth)

        # Track whether anything was found before the glob filter, so we can
        # distinguish a truly empty directory from a glob that matched nothing.
        had_files_before_filter = bool(files)

        # Apply glob filter
        if glob_pattern:
            import fnmatch
            files = [f for f in files if fnmatch.fnmatch(os.path.basename(f), glob_pattern)]

        # Sort and truncate
        files.sort()
        total = len(files)
        if total > 200:
            files = files[:200]

        if not files:
            # Distinguish "directory truly empty" from "glob filter excluded
            # everything". The LLM seeing "[Empty directory]" for a populated
            # dir (where only the glob didn't match) draws wrong conclusions.
            if glob_pattern and had_files_before_filter:
                return f"[No files matching '{glob_pattern}' in {path}]"
            return "[Empty directory]"

        lines = [f"[{total} files in {path}]"]
        for f in files:
            try:
                size = os.path.getsize(f)
                size_str = _format_size(size)
            except OSError:
                size_str = "?"
            lines.append(f"  {f}  ({size_str})")

        if total > 200:
            lines.append(f"  ... and {total - 200} more files")

        return "\n".join(lines)

    except Exception as e:
        return f"[ERROR] {e}"


def tool_glob(pattern: str, path: str = ".", max_results: int = 100, show_sizes: bool = False) -> str:
    """Find files by name pattern using glob syntax.

    Supports ** for recursive matching. Much faster than list_files for
    finding files by name because it uses pathlib.glob directly instead
    of listing everything then filtering.

    When inside a git repo, respects .gitignore (excludes __pycache__, build
    artifacts, node_modules, etc).

    Args:
        pattern: Glob pattern (e.g. '**/*.py', '*.txt', 'src/**/test_*.py').
        path: Root directory to search in (default: current).
        max_results: Maximum number of results to return (default 100).
        show_sizes: If True, show file sizes in output.

    Returns:
        List of matching file paths, sorted alphabetically.
    """
    try:
        # Clamp max_results to >=1. A value of 0 or negative produces an empty
        # result and the caller reports "[No files found matching pattern]"
        # even when matching files exist — misleading.
        max_results = max(1, max_results)
        p = Path(path)
        if not p.exists():
            return f"[ERROR] Path not found: {path}"
        if not p.is_dir():
            return f"[ERROR] Not a directory: {path}"

        matches = sorted(p.glob(pattern))
        # Filter out directories — only return files
        matches = [m for m in matches if m.is_file()]

        # Filter gitignored files when in a git repo — prevents wasting
        # LLM context tokens on __pycache__, node_modules, etc.
        git_ignored = _git_ignored_set(p)
        if git_ignored is not None:
            matches = [m for m in matches if str(m) not in git_ignored
                       and not any(str(m).startswith(ignored + os.sep) for ignored in git_ignored)]

        total = len(matches)
        if total == 0:
            return "[No files found matching pattern]"

        truncated = total > max_results
        if truncated:
            matches = matches[:max_results]

        lines = [f"[{total} file(s) matching '{pattern}' in {path}]"]
        for m in matches:
            # Show relative path from the search root for readability
            try:
                rel = m.relative_to(p)
            except ValueError:
                rel = m
            if show_sizes:
                try:
                    size = m.stat().st_size
                    lines.append(f"  {rel}  ({_format_size(size)})")
                except OSError:
                    lines.append(f"  {rel}  (?)")
            else:
                lines.append(f"  {rel}")

        if truncated:
            lines.append(f"  ... and {total - max_results} more files")

        return "\n".join(lines)

    except Exception as e:
        return f"[ERROR] {e}"


def tool_rename(source: str, destination: str) -> str:
    """Rename or move a file or directory.

    Works across directories (acts as a move). Refuses to overwrite
    existing files at the destination.

    Args:
        source: Current path of the file or directory.
        destination: New path for the file or directory.

    Returns:
        Confirmation or error message.
    """
    try:
        if not source:
            return "[ERROR] source path cannot be empty"
        if not destination:
            return "[ERROR] destination path cannot be empty"

        src = Path(source)
        dst = Path(destination)

        if not src.exists():
            return f"[ERROR] Source not found: {source}"
        if dst.exists():
            return f"[ERROR] Destination already exists: {destination}"

        # Create parent directories if needed (e.g. moving to a new subdir)
        dst.parent.mkdir(parents=True, exist_ok=True)

        src.rename(dst)
        return f"[OK] Renamed {source} → {destination}"

    except Exception as e:
        return f"[ERROR] {e}"


# ─── File backup helpers ─────────────────────────────────────────────
# When write_file or edit_file overwrites an existing file, we save the
# old content to .yoyo/backups/ so users can recover from LLM mistakes.
# Backups are named with a timestamp and sequence number to preserve
# ordering. We cap at 10 backups per file to avoid unbounded disk growth.

_BACKUP_DIR_NAME = ".yoyo"
_BACKUP_SUBDIR = "backups"
_MAX_BACKUPS_PER_FILE = 10


def _backup_file(path: Path) -> None:
    """Back up a file to .yoyo/backups/ before overwriting.

    Only backs up if the file exists. Creates the backup directory if needed.
    Cleans up old backups beyond _MAX_BACKUPS_PER_FILE for the same file.
    """
    if not path.exists() or not path.is_file():
        return

    # Never back up files inside .yoyo/ itself — avoids recursion
    # when writing to .yoyo/backups/ or other .yoyo/ locations
    try:
        path.resolve().relative_to(Path(_BACKUP_DIR_NAME).resolve())
        return  # File is inside .yoyo/, skip backup
    except ValueError:
        pass  # File is outside .yoyo/, proceed with backup

    try:
        from datetime import datetime

        backup_dir = Path(_BACKUP_DIR_NAME) / _BACKUP_SUBDIR
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create a safe filename: sanitize the original path
        # e.g. "src/agent.py" -> "src_agent.py_20260613_143022_001.bak"
        safe_name = str(path).replace(os.sep, "_").replace("/", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{safe_name}_{timestamp}.bak"

        # Avoid collision with existing backups (rare but possible)
        counter = 1
        backup_path = backup_dir / backup_name
        while backup_path.exists():
            backup_name = f"{safe_name}_{timestamp}_{counter}.bak"
            backup_path = backup_dir / backup_name
            counter += 1

        import shutil
        shutil.copy2(str(path), str(backup_path))

        # Clean up old backups for this file (keep most recent N)
        prefix = safe_name + "_"
        existing = sorted(
            [f for f in backup_dir.iterdir() if f.name.startswith(prefix)],
            key=lambda f: f.name,
        )
        while len(existing) > _MAX_BACKUPS_PER_FILE:
            oldest = existing.pop(0)
            try:
                oldest.unlink()
            except OSError:
                pass
    except Exception:
        # Backup failure should never block the actual write operation
        pass


# ─── Gitignore-aware helpers ─────────────────────────────────────────

def _git_list_files(directory: Path, max_depth: int | None = None) -> list[str] | None:
    """List files using git, respecting .gitignore.

    Returns a list of absolute file paths, or None if not inside a git repo.
    Uses `git ls-files` for tracked files + `git ls-files --others --exclude-standard`
    for untracked-but-not-ignored files.
    """
    try:
        # Quick check: are we inside a git repo?
        check = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5,
        )
        if check.returncode != 0:
            return None

        # Tracked files
        cmd_tracked = ["git", "-C", str(directory), "ls-files", "-z"]
        result_tracked = subprocess.run(cmd_tracked, capture_output=True, timeout=15)

        # Untracked but not gitignored files
        cmd_untracked = [
            "git", "-C", str(directory), "ls-files",
            "--others", "--exclude-standard", "-z",
        ]
        result_untracked = subprocess.run(cmd_untracked, capture_output=True, timeout=15)

        # Parse null-separated output (-z flag for safe filename handling)
        files = []
        for result in (result_tracked, result_untracked):
            if result.returncode == 0 and result.stdout:
                for name in result.stdout.decode("utf-8", errors="replace").split("\0"):
                    name = name.strip()
                    if not name:
                        continue
                    full_path = os.path.join(str(directory), name)
                    # Apply max_depth filter: depth = number of path separators relative to root
                    if max_depth:
                        depth = name.count(os.sep)
                        if depth >= max_depth:
                            continue
                    files.append(full_path)

        return files if files else []

    except Exception:
        # Timeout, git not installed, or not a repo — treat as non-git.
        return None


def _find_all_files(directory: Path, max_depth: int | None = None) -> list[str]:
    """List all files using find command, with os.walk fallback.

    Used when not inside a git repo (no .gitignore filtering).
    """
    # -maxdepth MUST come before -type/-name predicates. GNU find warns
    # ("you have specified the -maxdepth option after a non-option argument")
    # and some BusyBox finds error out entirely when the order is wrong.
    cmd = ["find", str(directory)]
    if max_depth:
        cmd.extend(["-maxdepth", str(max_depth)])
    cmd.extend(["-type", "f"])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

    if result.returncode != 0:
        # Fallback to os.walk
        files = []
        for root, dirs, filenames in os.walk(directory):
            if max_depth:
                depth = root.replace(str(directory), "").count(os.sep)
                if depth >= max_depth:
                    dirs.clear()
                    continue
            for f in filenames:
                files.append(os.path.join(root, f))
        return files
    else:
        return result.stdout.strip().splitlines()


def _git_ignored_set(directory: Path) -> set[str] | None:
    """Return a set of gitignored file paths (absolute), or None if not a git repo.

    Used by glob to filter out gitignored matches.
    Returns None when not in a git repo (caller should skip filtering).
    """
    try:
        check = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5,
        )
        if check.returncode != 0:
            return None

        # Get all files that git would ignore
        # `git ls-files --others --ignored --exclude-standard` lists ignored files
        result = subprocess.run(
            ["git", "-C", str(directory), "ls-files",
             "--others", "--ignored", "--exclude-standard", "-z"],
            capture_output=True, timeout=15,
        )
        if result.returncode != 0 or not result.stdout:
            return set()

        ignored = set()
        for name in result.stdout.decode("utf-8", errors="replace").split("\0"):
            name = name.strip()
            if name:
                ignored.add(os.path.join(str(directory), name))
        return ignored

    except Exception:
        # Timeout, git not installed, or not a repo — treat as non-git.
        return None


# ─── Tool schemas (OpenAI function calling format) ──────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command. Use for builds, tests, git, installing packages, and any system interaction. Returns combined stdout+stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Max seconds to wait (default 120, max 600).",
                        "default": 120,
                    },
                    "workdir": {
                        "type": "string",
                        "description": "Working directory (default: current).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file with line numbers. Use offset and limit for large files. Cannot read binary files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to read.",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Starting line number (1-indexed, default 1).",
                        "default": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max lines to read (default 500, max 2000).",
                        "default": 500,
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file. Writes the entire content. For surgical edits, use edit_file instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to write.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full content to write to the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Surgical text replacement in a file. Finds old_string and replaces with new_string. Use for targeted edits instead of rewriting entire files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to edit.",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Text to find (must be unique unless replace_all=True).",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement text. Use empty string to delete.",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences instead of requiring uniqueness.",
                        "default": False,
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search file contents with regex pattern. Returns matching lines with file paths and line numbers. Uses ripgrep if available, falls back to grep.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (default: current).",
                        "default": ".",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "Optional file filter (e.g. '*.py').",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 50).",
                        "default": 50,
                    },
                    "context": {
                        "type": "integer",
                        "description": "Number of context lines before and after each match (default 0, like grep -C).",
                        "default": 0,
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory with sizes. Supports glob filtering and depth limits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory to list (default: current).",
                        "default": ".",
                    },
                    "glob_pattern": {
                        "type": "string",
                        "description": "Filter by glob pattern (e.g. '*.py').",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum directory depth (None = unlimited).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mkdir",
            "description": "Create a directory. Supports creating parent directories with parents=True.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to create.",
                    },
                    "parents": {
                        "type": "boolean",
                        "description": "If True, create parent directories as needed (default True).",
                        "default": True,
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files by name pattern using glob syntax. Supports ** for recursive matching. Use for finding files by name or extension — much faster than list_files for file discovery.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g. '**/*.py', '*.txt', 'src/**/test_*.py').",
                    },
                    "path": {
                        "type": "string",
                        "description": "Root directory to search in (default: current).",
                        "default": ".",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 100).",
                        "default": 100,
                    },
                    "show_sizes": {
                        "type": "boolean",
                        "description": "If True, show file sizes in output.",
                        "default": False,
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Copy a file to a new location. Creates parent directories if needed. Refuses to overwrite existing files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Source file path.",
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination file path. Can be a directory (copies into it with same filename).",
                    },
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename",
            "description": "Rename or move a file or directory. Works across directories. Refuses to overwrite existing files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Current path of the file or directory.",
                    },
                    "destination": {
                        "type": "string",
                        "description": "New path for the file or directory.",
                    },
                },
                "required": ["source", "destination"],
            },
        },
    },
]

# Tool name → function mapping
TOOL_FUNCTIONS = {
    "bash": tool_bash,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
    "search": tool_search,
    "list_files": tool_list_files,
    "mkdir": tool_mkdir,
    "glob": tool_glob,
    "copy_file": tool_copy_file,
    "rename": tool_rename,
}


# ─── Helpers ─────────────────────────────────────────────────────────

def _truncate(text: str, max_bytes: int = 50000) -> str:
    """Truncate text to approximate byte limit, preserving valid UTF-8."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    # Walk back from the cut point to find a valid UTF-8 boundary
    # so we don't split multi-byte characters
    cut = max_bytes
    while cut > 0 and (encoded[cut] & 0xC0) == 0x80:
        cut -= 1
    return encoded[:cut].decode("utf-8") + f"\n... [truncated, {len(encoded)} bytes total]"


def _is_binary(path: Path) -> bool:
    """Check if a file appears to binary by scanning the first 8KB.

    Reads only the first 8KB via a file handle — NOT the whole file.
    (Previously used path.read_bytes()[:8192], which loaded the entire
    file into memory before slicing, causing OOM on multi-GB files.)
    """
    try:
        with path.open("rb") as fh:
            chunk = fh.read(8192)
        return b"\x00" in chunk
    except Exception:
        return True


def _format_size(size: int) -> str:
    """Format file size in human-readable form."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f}{unit}"
        size /= 1024
    return f"{size:.0f}TB"
