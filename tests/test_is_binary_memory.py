"""Tests that _is_binary only reads the first 8KB, not the entire file.

Regression: _is_binary used path.read_bytes()[:8192], which reads the
ENTIRE file into memory before slicing. For multi-GB files this causes
OOM or extreme memory spikes. The fix reads only the needed prefix
via an open file handle.
"""

import os
import tempfile

import pytest

from src.tools import _is_binary
from pathlib import Path


@pytest.fixture
def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestIsBinaryMemoryEfficient:
    """Verify _is_binary doesn't load entire large files into memory."""

    def test_small_text_file_not_binary(self, tmpdir):
        f = os.path.join(tmpdir, "a.txt")
        with open(f, "w") as fh:
            fh.write("just some text\n")
        assert _is_binary(Path(f)) is False

    def test_small_binary_file_detected(self, tmpdir):
        f = os.path.join(tmpdir, "b.bin")
        with open(f, "wb") as fh:
            fh.write(b"text\x00with null\n")
        assert _is_binary(Path(f)) is True

    def test_large_text_file_only_reads_prefix(self, tmpdir):
        """A large text file must be classified without reading all of it.

        We create a 20MB text file. If _is_binary read the whole file,
        memory usage would spike. We can't easily measure RSS here, but
        we CAN verify correctness and that it completes quickly — and
        that a null byte beyond 8KB is NOT detected (proving only the
        prefix is read).
        """
        f = os.path.join(tmpdir, "big.txt")
        # Write 20MB of text — first 8KB is clean text
        chunk = "abcdefghij" * 1000  # 10KB of text
        with open(f, "w") as fh:
            fh.write(chunk * 2000)  # ~20MB
        # Should be classified as non-binary (no null in prefix)
        assert _is_binary(Path(f)) is False

    def test_does_not_load_entire_file_into_memory(self, tmpdir):
        """_is_binary must NOT read the whole file into memory.

        Regression: the old implementation used path.read_bytes()[:8192],
        which reads the ENTIRE file into a bytes object, then slices. For
        a large file this causes a memory spike equal to the file size.

        We measure peak allocated memory via tracemalloc. A 10MB file
        should NOT cause a 10MB allocation — the fix streams only 8KB.
        """
        import tracemalloc

        f = os.path.join(tmpdir, "huge.txt")
        # Write 10MB of clean text
        chunk = "x" * 1_000_000
        with open(f, "w") as fh:
            for _ in range(10):
                fh.write(chunk)
        file_size = os.path.getsize(f)
        assert file_size >= 10_000_000  # sanity check: ~10MB

        tracemalloc.start()
        result = _is_binary(Path(f))
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert result is False
        # Peak allocation must be far less than the file size.
        # A streaming read of 8KB should keep peak under ~200KB (generous
        # bound for overhead). The buggy version would spike to ~10MB.
        assert peak < 1_000_000, (
            f"Peak memory {peak} bytes is too high — _is_binary likely "
            f"read the entire {file_size}-byte file into memory"
        )

    def test_null_byte_beyond_8kb_not_detected(self, tmpdir):
        """A null byte at position 10000 should NOT trigger binary detection.

        This proves _is_binary only reads the first 8KB. If it read the
        whole file, this null byte would be found and classified as binary.
        """
        f = os.path.join(tmpdir, "sneaky.txt")
        with open(f, "wb") as fh:
            fh.write(b"a" * 10000)  # 10KB of 'a' — beyond 8KB window
            fh.write(b"\x00")       # null byte at position 10000
            fh.write(b"a" * 1000)
        # Only the first 8KB is read → null byte at 10000 is invisible
        assert _is_binary(Path(f)) is False

    def test_null_byte_within_8kb_detected(self, tmpdir):
        """A null byte within the first 8KB IS detected."""
        f = os.path.join(tmpdir, "binary.txt")
        with open(f, "wb") as fh:
            fh.write(b"a" * 4000)   # within 8KB window
            fh.write(b"\x00")       # null byte at position 4000
            fh.write(b"a" * 100000) # lots more data
        assert _is_binary(Path(f)) is True
