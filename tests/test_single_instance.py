# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from src.single_instance import ERROR_ALREADY_EXISTS, SingleInstance, SingleInstanceError


class SingleInstanceTests(unittest.TestCase):
    def test_first_instance_acquires_and_releases_mutex(self) -> None:
        kernel32 = Mock()
        kernel32.CreateMutexW.return_value = 101
        kernel32.GetLastError.return_value = 0
        kernel32.CloseHandle.return_value = True

        with patch("src.single_instance._kernel32", kernel32):
            instance = SingleInstance()
            self.assertTrue(instance.acquire())
            instance.release()
            instance.release()

        kernel32.CreateMutexW.assert_called_once_with(
            None, False, r"Local\scrcpy-launcher-tray"
        )
        kernel32.CloseHandle.assert_called_once_with(101)

    def test_duplicate_instance_closes_duplicate_handle(self) -> None:
        kernel32 = Mock()
        kernel32.CreateMutexW.return_value = 202
        kernel32.GetLastError.return_value = ERROR_ALREADY_EXISTS
        kernel32.CloseHandle.return_value = True

        with patch("src.single_instance._kernel32", kernel32):
            instance = SingleInstance()
            self.assertFalse(instance.acquire())
            instance.release()

        kernel32.CloseHandle.assert_called_once_with(202)

    def test_mutex_api_failure_reports_windows_error(self) -> None:
        kernel32 = Mock()
        kernel32.CreateMutexW.return_value = 0
        kernel32.GetLastError.return_value = 5

        with patch("src.single_instance._kernel32", kernel32):
            with self.assertRaisesRegex(SingleInstanceError, "Windows error 5"):
                SingleInstance().acquire()


if __name__ == "__main__":
    unittest.main()
