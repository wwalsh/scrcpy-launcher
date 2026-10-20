# SPDX-License-Identifier: GPL-3.0-only

"""Trusted scrcpy bundle inventory compiled into scrcpy-launcher."""

from __future__ import annotations

BUNDLED_SCRCPY_VERSION = "5.0.1"

# Keep synchronized with packaging/dependencies/scrcpy-win64-v5.0.1.json.
BUNDLED_FILE_HASHES = {
    "AdbWinApi.dll": "c1d653030b4bde65d3e07e4d0b0979e17be56df1436cdd15528630f27808050d",
    "scrcpy.exe": "64bcee493d9243dab1e84093928014348738e31f3225e67558210e6b6cfb9cd6",
    "AdbWinUsbApi.dll": "0710e894d9b40f71a670c13c694079d564c92c1279da382cfe4850983aaebe1b",
    "avutil-61.dll": "52eb504ced0ea6d9e936d348df51c8aaeec1cae8fa4a7dba339fea87d7cce725",
    "scrcpy.png": "8e8ca237898faa16014cdd118396af53405b423f3db0508c50cc3edce08eb313",
    "open_a_terminal_here.bat": "843758795a84d0d035a7d277ad29cc1ff1702048b4b61ae74b9e3439ae683423",
    "scrcpy-server": "764eb6f79811d5211fe9df341120882ba9994c7a61b897d7bf3fb662e53bc536",
    "avcodec-63.dll": "159928e3bbe7beaca046ccf831fdf44f1e5559c0e63417f007889a6bb2c5de88",
    "avformat-63.dll": "4dbb0c1c8262f7ae45e7edc4866e26f53b358bf4fc7a0b971f15d1f2d7baf22f",
    "swresample-7.dll": "7b57e891bf09c43422d79f98cf9d1830c4b1d48a251423ce5fb8c2048eb8fc1e",
    "disconnected.png": "e394873cd3e2cc3ab0cca6212b10ed2a8a0fad11a05675c8a9fa6f26f3ae12c0",
    "libusb-1.0.dll": "0c82e969c046d816507a2fe1e57253a334cb203bd6ea223194ad17c007154f32",
    "SDL3.dll": "288aaf5b4f246bd84c276351867e3132cfcd9b0a9d25fb679c8d94b30cdf333e",
    "LICENSE.txt": "01c12035bf35af37241298dc7ad538eb2a07e5c940437bc6876feeaa9d1951d0",
    "adb.exe": "b4a6b455702684652cccf7b46258b29e653538904359a58fd4931cf3ef286b3f",
    "scrcpy-noconsole.vbs": "3ccda94c161f18cef07c50d4d3c4913eb883d4b0fe3b939c35fae52784fb1d2b",
}
