# SPDX-License-Identifier: GPL-3.0-only

"""Trusted scrcpy bundle inventory compiled into scrcpy-launcher."""

from __future__ import annotations

BUNDLED_SCRCPY_VERSION = "4.1"

# Keep synchronized with packaging/dependencies/scrcpy-win64-v4.1.json.
BUNDLED_FILE_HASHES = {
    "adb.exe": "957e46b8615f7af5b7292a2ddabe98d2e61940c3fb2b0545756507f080613e71",
    "AdbWinApi.dll": "120bef587119c6cb926b86b9be90fdfbce38937588eae28cd91a94ce63c7b965",
    "AdbWinUsbApi.dll": "6ca69a2ca0e31309c087d288f058977d421ad03500e4c3e1dbd981241a069c60",
    "avcodec-62.dll": "7179de2b132e78eb0a76458a0a3859dfe1edcbb6d2eeb4a456f03f7ae96d5b66",
    "avformat-62.dll": "7232316acce00371d89f589748b570d95885ea6bbfc1972a0a9d3b884903eee1",
    "avutil-60.dll": "3d6170dd68549c6f39b8d8710a37f79d9678905df705a8b0a6bc7ea9037daddf",
    "disconnected.png": "e394873cd3e2cc3ab0cca6212b10ed2a8a0fad11a05675c8a9fa6f26f3ae12c0",
    "libusb-1.0.dll": "8ec130918a476b0dbd114c803e71314360608ceabdd2b6f38c83f6f208c608e0",
    "LICENSE.txt": "01c12035bf35af37241298dc7ad538eb2a07e5c940437bc6876feeaa9d1951d0",
    "open_a_terminal_here.bat": "843758795a84d0d035a7d277ad29cc1ff1702048b4b61ae74b9e3439ae683423",
    "scrcpy-noconsole.vbs": "3ccda94c161f18cef07c50d4d3c4913eb883d4b0fe3b939c35fae52784fb1d2b",
    "scrcpy-server": "deacb991ed2509715160ffdc7907e47b4160eb30d1566217e9047fd5b8850cae",
    "scrcpy.exe": "575ca1284345c7b3975585bc61b66d564a9a4f1ecb28fbb4c599c92a124054a9",
    "scrcpy.png": "8e8ca237898faa16014cdd118396af53405b423f3db0508c50cc3edce08eb313",
    "SDL3.dll": "0619eb2da6032984dc6e2098897aeacdbd66b0415bb87bc03e628159ba60b15d",
    "swresample-6.dll": "4cc809d2cd822e186906fbc9d8a0acffa937e35de1282b2e2ab7346cfed96fed",
}
