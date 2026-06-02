"""Built-in tools — the agent's hands for interacting with the world.

Each tool is:
1. A Python function that does the work
2. An OpenAI-format function schema for the LLM to understand

Tools: bash, read_file, write_file, edit_file, search, list_files, mkdir, glob, rename
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
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir or os.getcwd(),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n--- stderr ---\n" + result.stderr) if output else result.stderr

        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"

        return _truncate(output, 50000)

    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] Command timed out after {timeout}s"
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
    try:
        p = Path(path)
        if not p.exists():
            return f"[ERROR] File not found: {path}"
        if not p.is_file():
            return f"[ERROR] Not a file: {path}"
        if _is_binary(p):
            return f"[ERROR] Binary file, cannot read: {path}"

        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)

        # 1-indexed offset
        start = max(0, offset - 1)
        end = min(total, start + limit)

        selected = lines[start:end]
        numbered = [f"{i + 1:>6}|{line}" for i, line in enumerate(selected, start=start + 1)]

        header = f"[File: {path} ({total} lines)]\n"
        if start > 0 or end < total:
            header += f"[Showing lines {start + 1}-{end} of {total}]\n"

        return header + "\n".join(numbered)

    except Exception as e:
        return f"[ERROR] {e}"


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
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        line_count = content.count("\n") + (0 if content.endswith("\n") else 1)
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


def tool_search(pattern: str, path: str = ".", file_glob: str | None = None, max_results: int = 50) -> str:
    """Search file contents with regex, or find files by name pattern.

    Args:
        pattern: Regex pattern to search for in file contents, or glob like '*.py' to find by name.
        path: Directory to search in (default: current).
        file_glob: Optional file filter (e.g. '*.py').
        max_results: Max results to return (default 50).

    Returns:
        Matching lines with file paths and line numbers.
    """
    try:
        # Build ripgrep command
        cmd = ["rg", "--line-number", "--max-count", str(max_results)]
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

        output = result.stdout.strip()
        return _truncate(output, 50000)

    except FileNotFoundError:
        # Fallback to grep if rg not installed
        cmd = ["grep", "-rn", "-E", pattern]
        if file_glob:
            cmd.extend(["--include", file_glob])
        cmd.extend([path])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return "[No matches found]"
            return _truncate(result.stdout.strip(), 50000)
        except Exception as e:
            return f"[ERROR] {e}"
    except subprocess.TimeoutExpired:
        return "[TIMEOUT] Search timed out"
    except Exception as e:
        return f"[ERROR] {e}"


def tool_list_files(path: str = ".", glob_pattern: str | None = None, max_depth: int | None = None) -> str:
    """List files in a directory.

    Args:
        path: Directory to list (default: current).
        glob_pattern: Filter by glob pattern (e.g. '*.py').
        max_depth: Maximum directory depth (None = unlimited).

    Returns:
        Sorted file listing with sizes.
    """
    try:
        p = Path(path)
        if not p.exists():
            return f"[ERROR] Path not found: {path}"
        if not p.is_dir():
            return f"[ERROR] Not a directory: {path}"

        # Build find command for efficiency
        cmd = ["find", path, "-type", "f"]
        if max_depth:
            cmd.extend(["-maxdepth", str(max_depth)])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        if result.returncode != 0:
            # Fallback to os.walk
            files = []
            for root, dirs, filenames in os.walk(path):
                if max_depth:
                    depth = root.replace(str(p), "").count(os.sep)
                    if depth >= max_depth:
                        dirs.clear()
                        continue
                for f in filenames:
                    files.append(os.path.join(root, f))
        else:
            files = result.stdout.strip().splitlines()

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

    Args:
        pattern: Glob pattern (e.g. '**/*.py', '*.txt', 'src/**/test_*.py').
        path: Root directory to search in (default: current).
        max_results: Maximum number of results to return (default 100).
        show_sizes: If True, show file sizes in output.

    Returns:
        List of matching file paths, sorted alphabetically.
    """
    try:
        p = Path(path)
        if not p.exists():
            return f"[ERROR] Path not found: {path}"
        if not p.is_dir():
            return f"[ERROR] Not a directory: {path}"

        matches = sorted(p.glob(pattern))
        # Filter out directories — only return files
        matches = [m for m in matches if m.is_file()]

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
    """Check if a file appears to be binary."""
    try:
        chunk = path.read_bytes()[:8192]
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
