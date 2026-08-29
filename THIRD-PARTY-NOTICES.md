# Third-party notices

scrcpy-launcher is licensed under `GPL-3.0-only`. The packaged Windows
application is an aggregate that also contains separately licensed runtime
components. Those components remain under their original licenses; nothing in
the scrcpy-launcher license changes their terms.

Exact component versions are determined and recorded by the release build. The
license texts shipped in `licenses/` apply to the corresponding components.

## Components distributed in the current package

| Component | Distribution role | License | Source and notices |
| --- | --- | --- | --- |
| CPython and Python standard library | Embedded runtime and standard-library modules | PSF-2.0 and historical component licenses | <https://github.com/python/cpython>; see `licenses/Python-3.14.txt`, which also contains notices for bzip2, libffi, and Zstandard components shipped by CPython. |
| pywin32 | Win32 tray, process, and system integration modules | BSD-3-Clause-style pywin32 license | <https://github.com/mhammond/pywin32>; see `licenses/pywin32.txt`. |
| Tcl/Tk | tkinter settings user interface | TCL | <https://www.tcl-lang.org/>; see `licenses/Tcl-Tk.txt`. |
| PyInstaller bootloader and related files | Bootstraps the packaged executable | GPL-2.0-or-later with the PyInstaller Bootloader Exception; runtime hooks are Apache-2.0 | <https://github.com/pyinstaller/pyinstaller>; see `licenses/PyInstaller.txt` and `licenses/Apache-2.0.txt`. The PyInstaller build tool itself is not included as a standalone program. |
| NSIS installer runtime and compression modules | Implements the Windows setup and uninstaller executables | zlib/libpng, bzip2, and CPL-1.0 components | <https://nsis.sourceforge.io/>; see `licenses/NSIS.txt`. |
| OpenSSL 3 libraries | TLS and cryptographic support used by the Python runtime | Apache-2.0 | <https://www.openssl.org/source/>; see `licenses/Apache-2.0.txt`. |
| zlib | Compression support used by the Python runtime | Zlib | <https://zlib.net/>; see `licenses/Zlib.txt`. |
| Microsoft Visual C++ runtime files | Windows C/C++ runtime required by the packaged executable | Microsoft Visual Studio redistributable terms | <https://visualstudio.microsoft.com/license-terms/>. |

The CPython distribution includes additional standard-library modules and
notices. Its complete license file is included instead of attempting to replace
that upstream inventory with a summary.

## Build tools not distributed as standalone programs

- PyInstaller creates the application directory. Its embedded bootloader and
  runtime hooks are covered above.
- NSIS compiles the Windows installer but is not installed as a standalone tool
  with scrcpy-launcher. Its generated installer runtime is covered above.

## Bundled scrcpy distribution

Release builds bundle the unmodified official scrcpy 4.1 Windows x64 archive
under `tools/scrcpy`. The acquisition manifest pins the release URL, archive
SHA-256, complete file inventory, and per-file hashes. The generated
`tools/scrcpy/BUNDLE-METADATA.json` records the same provenance in each package.

| Component | Distributed files or role | License | Source and notices |
| --- | --- | --- | --- |
| scrcpy client and `scrcpy-server` 4.1 | `scrcpy.exe`, `scrcpy-server`, scripts and images | Apache-2.0 | <https://github.com/Genymobile/scrcpy/tree/v4.1>; see `tools/scrcpy/LICENSE.txt` and `licenses/Apache-2.0.txt`. |
| Android SDK Platform-Tools 37.0.0 | `adb.exe`, `AdbWinApi.dll`, `AdbWinUsbApi.dll` | Apache-2.0 and notices identified by the upstream distribution | <https://android.googlesource.com/platform/packages/modules/adb/>; see `licenses/Apache-2.0.txt` and generated `licenses/Android-Platform-Tools-NOTICE.txt`. |
| FFmpeg 8.1.2 | `avcodec-62.dll`, `avformat-62.dll`, `avutil-60.dll`, `swresample-6.dll` | LGPL-2.1-or-later for the configuration used by scrcpy | <https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz>; see generated `licenses/FFmpeg-LGPL-2.1.txt`. The verified source archive is published beside release artifacts. |
| dav1d 1.5.3 | Statically linked AV1 decoder used by the FFmpeg libraries | BSD-2-Clause | <https://code.videolan.org/videolan/dav1d/-/tree/1.5.3>; see `licenses/dav1d-BSD-2-Clause.txt`. |
| SDL 3.4.12 | `SDL3.dll` | Zlib | <https://github.com/libsdl-org/SDL/tree/release-3.4.12>; see generated `licenses/SDL-Zlib.txt`. The verified source archive is published beside release artifacts. |
| libusb 1.0.30 | `libusb-1.0.dll` | LGPL-2.1-or-later | <https://github.com/libusb/libusb/tree/v1.0.30>; see generated `licenses/libusb-LGPL-2.1.txt`. The verified source archive is published beside release artifacts. |
| zlib | Statically linked compression support in the FFmpeg build | Zlib | <https://zlib.net/>; see `licenses/Zlib.txt`. |

The FFmpeg build configuration used by scrcpy does not enable FFmpeg's optional
GPL components. FFmpeg and libusb are separate, replaceable DLLs; they have not
been modified by scrcpy-launcher.

## Release provenance requirements

Before any acquired binary is added to an installer or portable archive, its
release record must contain:

- component name, version, and distributed file names;
- official binary download URL and source-code URL;
- SHA-256 of the downloaded archive;
- applicable license expression and bundled license/NOTICE files;
- whether the binary or its packaging was modified;
- corresponding-source location or written-offer requirement, when applicable;
- destination paths in the final package; and
- a reproducible mapping from the verified archive to those destination files.

A release build must fail closed if its pinned version, hash, required files, or
required notices do not match. Bundled third-party components must never be
described as relicensed under `GPL-3.0-only` merely because they share an
installer with scrcpy-launcher.

## Source availability

The corresponding source for scrcpy-launcher is the source tree and tagged
source archive published with each binary release. Upstream source locations for
separately licensed components are listed above. The exact source archives used
for FFmpeg, libusb, and SDL are copied to `dist/artifacts/sources` with
SHA-256 sidecars by a release build. The verified Platform-Tools archive is
included there to preserve its complete upstream NOTICE material and binary
provenance. Exact URLs and hashes are recorded in `SOURCE-METADATA.json` and the
pinned dependency manifest.
