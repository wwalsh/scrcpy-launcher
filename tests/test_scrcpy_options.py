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

    def test_get_value_reads_split_form(self) -> None:
        self.assertEqual(get_value(["--serial", "ABC", "--no-audio"], "--serial"), "ABC")

    def test_get_value_does_not_consume_another_option_as_a_split_value(self) -> None:
        self.assertEqual(
            get_value(["--serial", "--no-audio"], "--serial"),
            "",
        )

    def test_set_value_replaces_split_form_and_preserves_order(self) -> None:
        args = ["--before", "--serial", "ABC", "--after"]
        self.assertEqual(
            set_value(args, "--serial", "XYZ"),
            ["--before", "--serial=XYZ", "--after"],
        )

    def test_set_value_removes_mixed_duplicate_forms(self) -> None:
        args = ["--serial=one", "--keep", "--serial", "two", "--serial=three"]
        self.assertEqual(set_value(args, "--serial", ""), ["--keep"])

    def test_set_value_missing_split_value_removes_only_option(self) -> None:
        self.assertEqual(
            set_value(["--before", "--serial"], "--serial", "new"),
            ["--before", "--serial=new"],
        )
        self.assertEqual(
            set_value(["--before", "--serial"], "--serial", ""),
            ["--before"],
        )

    def test_set_value_does_not_consume_following_option_as_missing_value(self) -> None:
        args = ["--serial", "--window-title", "Title", "--after"]
        self.assertEqual(
            set_value(args, "--serial", "ABC"),
            ["--serial=ABC", "--window-title", "Title", "--after"],
        )


if __name__ == "__main__":
    unittest.main()
