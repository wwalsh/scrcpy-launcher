# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import unittest

from src.scrcpy_options import get_value, has_flag, set_flag, set_value


class ScrcpyOptionTests(unittest.TestCase):
    def test_value_option_add_replace_remove_and_deduplicate(self) -> None:
        args = ["--no-audio", "--window-title=Old", "--window-title=Duplicate"]

        updated = set_value(args, "--window-title", "New")
        self.assertEqual(updated, ["--no-audio", "--window-title=New"])
        self.assertEqual(get_value(updated, "--window-title"), "New")
        self.assertEqual(set_value(updated, "--window-title", ""), ["--no-audio"])

    def test_flag_changes_preserve_unknown_arguments(self) -> None:
        args = ["--serial=ABC", "--custom=value"]

        enabled = set_flag(args, "--no-audio", True)
        self.assertEqual(enabled, ["--serial=ABC", "--custom=value", "--no-audio"])
        self.assertEqual(set_flag(enabled, "--no-audio", False), args)

    def test_new_display_value_counts_as_enabled_and_is_preserved(self) -> None:
        args = ["--new-display=1920x1080/420", "--start-app=com.example"]

        self.assertTrue(has_flag(args, "--new-display", allow_value=True))
        self.assertEqual(set_flag(args, "--new-display", True, allow_value=True), args)
        self.assertEqual(
            set_flag(args, "--new-display", False, allow_value=True),
            ["--start-app=com.example"],
        )


if __name__ == "__main__":
    unittest.main()
