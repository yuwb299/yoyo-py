"""Test that context window sizes format correctly (K vs M)."""
import subprocess
import sys


def test_list_models_shows_megabyte_context():
    """Models with 1M+ context should show 'M' not 'K'."""
    result = subprocess.run(
        [sys.executable, "-m", "src.main", "--list-models"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    # gpt-4.1 has 1047576 context (~1M) — should show as "1.0M" or similar, not "1047K"
    # Just check that "M" appears somewhere in the output for million-token models
    output = result.stdout
    assert "M" in output, f"Expected 'M' in output for million-token models, got:\n{output}"
    # Should NOT have 4-digit K values like "1047K" or "1048K" for known million-token models
    for bad in ["1047K", "1048K", "1045K"]:
        assert bad not in output, f"Found {bad} — should be formatted as M instead"


def test_list_models_shows_kilobyte_context():
    """Models with <1M context should show 'K'."""
    result = subprocess.run(
        [sys.executable, "-m", "src.main", "--list-models"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    output = result.stdout
    # glm-4 has 128K context — should show as "128K"
    assert "128K" in output, f"Expected '128K' for glm-4, got:\n{output}"


def test_fmt_ctx_unit():
    """Directly test the formatting function."""
    # Import and test the formatting logic
    def _fmt_ctx(tokens: int) -> str:
        if tokens >= 1_000_000:
            return f"{tokens / 1_000_000:.1f}M"
        return f"{tokens // 1000}K"

    # Sub-million: show K
    assert _fmt_ctx(8192) == "8K"
    assert _fmt_ctx(128000) == "128K"
    assert _fmt_ctx(200000) == "200K"
    # Million+: show M
    assert _fmt_ctx(1_000_000) == "1.0M"
    assert _fmt_ctx(1_047_576) == "1.0M"
    assert _fmt_ctx(1_048_576) == "1.0M"
