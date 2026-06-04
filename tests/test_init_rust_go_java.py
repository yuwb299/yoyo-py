"""Tests for /init command with Rust, Go, and Java project detection."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.repl import _run_init_command


@pytest.fixture
def rust_project(tmp_path):
    """Create a minimal Rust project structure."""
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "my-rust-app"\nversion = "0.1.0"\nedition = "2021"\n'
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.rs").write_text('fn main() { println!("hello"); }')
    return str(tmp_path)


@pytest.fixture
def go_project(tmp_path):
    """Create a minimal Go project structure."""
    (tmp_path / "go.mod").write_text("module github.com/example/myapp\n\ngo 1.21\n")
    (tmp_path / "main.go").write_text('package main\nfunc main() { println("hello") }\n')
    return str(tmp_path)


@pytest.fixture
def java_project(tmp_path):
    """Create a minimal Maven Java project structure."""
    (tmp_path / "pom.xml").write_text(
        '<project><modelVersion>4.0.0</modelVersion>'
        '<groupId>com.example</groupId><artifactId>myapp</artifactId><version>1.0</version></project>'
    )
    (tmp_path / "src" / "main" / "java").mkdir(parents=True)
    return str(tmp_path)


class TestInitRust:
    """Test /init with Rust projects."""

    def test_detects_rust_project(self, rust_project):
        result = _run_init_command(workdir=rust_project)
        assert "YOYO.md" in result
        yoyo = Path(rust_project) / "YOYO.md"
        assert yoyo.exists()
        content = yoyo.read_text()
        assert "Rust" in content
        assert "cargo test" in content

    def test_extracts_rust_project_name(self, rust_project):
        _run_init_command(workdir=rust_project)
        yoyo = Path(rust_project) / "YOYO.md"
        content = yoyo.read_text()
        assert "my-rust-app" in content

    def test_no_overwrite_without_force(self, rust_project):
        _run_init_command(workdir=rust_project)
        result = _run_init_command(workdir=rust_project)
        assert "already exists" in result

    def test_force_overwrites(self, rust_project):
        _run_init_command(workdir=rust_project)
        result = _run_init_command(workdir=rust_project, force=True)
        assert "YOYO.md" in result or "created" in result.lower()


class TestInitGo:
    """Test /init with Go projects."""

    def test_detects_go_project(self, go_project):
        result = _run_init_command(workdir=go_project)
        assert "YOYO.md" in result
        yoyo = Path(go_project) / "YOYO.md"
        assert yoyo.exists()
        content = yoyo.read_text()
        assert "Go" in content
        assert "go test" in content

    def test_extracts_go_module_name(self, go_project):
        _run_init_command(workdir=go_project)
        yoyo = Path(go_project) / "YOYO.md"
        content = yoyo.read_text()
        assert "github.com/example/myapp" in content


class TestInitJava:
    """Test /init with Java/Maven projects."""

    def test_detects_java_project(self, java_project):
        result = _run_init_command(workdir=java_project)
        assert "YOYO.md" in result
        yoyo = Path(java_project) / "YOYO.md"
        assert yoyo.exists()
        content = yoyo.read_text()
        assert "Java" in content
        assert "mvn test" in content
