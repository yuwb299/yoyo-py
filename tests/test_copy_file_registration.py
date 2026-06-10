"""Tests for copy_file tool registration in TOOL_FUNCTIONS and TOOL_SCHEMAS.

Ensures the copy_file tool is properly registered so the agent can discover and call it.
Same pattern as test_rename_registration.py and test_mkdir_registration.py.
"""

from src.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, tool_copy_file


class TestCopyFileRegistration:

    def test_in_tool_functions(self):
        """copy_file must be in TOOL_FUNCTIONS so the agent can call it."""
        assert "copy_file" in TOOL_FUNCTIONS
        assert TOOL_FUNCTIONS["copy_file"] is tool_copy_file

    def test_has_schema(self):
        """copy_file must have a schema in TOOL_SCHEMAS."""
        schema_names = [s["function"]["name"] for s in TOOL_SCHEMAS]
        assert "copy_file" in schema_names

    def test_schema_has_required_params(self):
        """Schema must declare source and destination as required."""
        schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "copy_file")
        assert "source" in schema["function"]["parameters"]["properties"]
        assert "destination" in schema["function"]["parameters"]["properties"]
        assert schema["function"]["parameters"]["required"] == ["source", "destination"]
