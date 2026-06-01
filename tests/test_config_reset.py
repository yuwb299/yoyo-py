"""Test /config reset functionality."""

import unittest

from src.repl import _handle_config_command


class TestConfigReset(unittest.TestCase):
    """Test /config reset command restores defaults."""

    def test_config_reset_temperature(self):
        """Resetting temperature should return it to None (API default)."""
        output, updates = _handle_config_command(
            args_str="reset",
            temperature=0.9,
            max_tokens=4096,
            top_p=0.95,
            model="test-model",
        )
        self.assertIn("reset", output.lower())
        self.assertEqual(updates.get("temperature"), None)
        self.assertEqual(updates.get("max_tokens"), None)
        self.assertEqual(updates.get("top_p"), None)

    def test_config_reset_output_message(self):
        output, updates = _handle_config_command(
            args_str="reset",
            temperature=0.5,
            max_tokens=1024,
            top_p=0.8,
            model="test",
        )
        self.assertIn("[OK]", output)

    def test_config_set_then_reset(self):
        """Setting a value then resetting should clear it."""
        # Set temperature
        _, set_updates = _handle_config_command(
            args_str="temperature 0.7",
            temperature=None,
            max_tokens=None,
            top_p=None,
            model="test",
        )
        self.assertEqual(set_updates.get("temperature"), 0.7)

        # Reset
        _, reset_updates = _handle_config_command(
            args_str="reset",
            temperature=0.7,
            max_tokens=None,
            top_p=None,
            model="test",
        )
        self.assertEqual(reset_updates.get("temperature"), None)
        self.assertEqual(reset_updates.get("max_tokens"), None)
        self.assertEqual(reset_updates.get("top_p"), None)


if __name__ == "__main__":
    unittest.main()
