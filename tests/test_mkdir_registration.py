"""Test that tool_mkdir is properly registered and callable via the agent."""

import json
import pytest
from src.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, tool_mkdir


class TestMkdirRegistration:
    """Verify mkdir tool is registered in the tool system."""

    def test_mkdir_in_tool_functions(self):
        """tool_mkdir should be in the TOOL_FUNCTIONS mapping."""
        assert "mkdir" in TOOL_FUNCTIONS
        assert TOOL_FUNCTIONS["mkdir"] is tool_mkdir

    def test_mkdir_in_tool_schemas(self):
        """mkdir should have a schema entry in TOOL_SCHEMAS."""
        mkdir_schemas = [s for s in TOOL_SCHEMAS if s["function"]["name"] == "mkdir"]
        assert len(mkdir_schemas) == 1, f"Expected 1 mkdir schema, found {len(mkdir_schemas)}"

    def test_mkdir_schema_has_required_fields(self):
        """mkdir schema should have name, description, and parameters."""
        mkdir_schema = [s for s in TOOL_SCHEMAS if s["function"]["name"] == "mkdir"][0]
        func = mkdir_schema["function"]
        assert func["name"] == "mkdir"
        assert "description" in func
        assert "parameters" in func
        params = func["parameters"]["properties"]
        assert "path" in params
        assert params["path"]["type"] == "string"

    def test_mkdir_schema_path_is_required(self):
        """mkdir schema should require 'path' parameter."""
        mkdir_schema = [s for s in TOOL_SCHEMAS if s["function"]["name"] == "mkdir"][0]
        required = mkdir_schema["function"]["parameters"].get("required", [])
        assert "path" in required

    def test_mkdir_schema_has_parents_param(self):
        """mkdir schema should have 'parents' parameter with default True."""
        mkdir_schema = [s for s in TOOL_SCHEMAS if s["function"]["name"] == "mkdir"][0]
        params = mkdir_schema["function"]["parameters"]["properties"]
        assert "parents" in params
        assert params["parents"]["type"] == "boolean"
        assert params["parents"].get("default") is True


class TestMkdirFunctionality:
    """Verify tool_mkdir works correctly."""

    def test_mkdir_creates_directory(self, tmp_path):
        target = tmp_path / "new_dir"
        result = tool_mkdir(str(target))
        assert target.is_dir()
        assert "[OK]" in result

    def test_mkdir_with_parents(self, tmp_path):
        target = tmp_path / "a" / "b" / "c"
        result = tool_mkdir(str(target), parents=True)
        assert target.is_dir()
        assert "[OK]" in result

    def test_mkdir_already_exists(self, tmp_path):
        target = tmp_path / "existing"
        target.mkdir()
        result = tool_mkdir(str(target))
        assert "already exists" in result

    def test_mkdir_file_exists(self, tmp_path):
        target = tmp_path / "file.txt"
        target.write_text("hello")
        result = tool_mkdir(str(target))
        assert "[ERROR]" in result
        assert "not a directory" in result

    def test_mkdir_no_parents_fails_on_missing_parent(self, tmp_path):
        target = tmp_path / "a" / "b"
        result = tool_mkdir(str(target), parents=False)
        assert "[ERROR]" in result
