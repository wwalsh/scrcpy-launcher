# SPDX-License-Identifier: GPL-3.0-only

"""Generate the Windows version resource consumed by PyInstaller."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: generate_version_info.py <version> <output_path>")
    version = sys.argv[1]
    parts = version.split(".")
    if len(parts) not in (3, 4) or any(not part.isdigit() for part in parts):
        raise SystemExit(f"Version must contain three or four numeric parts: {version}")
    numbers = [int(part) for part in parts]
    while len(numbers) < 4:
        numbers.append(0)
    version_tuple = tuple(numbers)
    output_path = Path(sys.argv[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'scrcpy-launcher contributors'),
         StringStruct('FileDescription', 'scrcpy-launcher Windows tray application'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', 'scrcpy-launcher'),
         StringStruct('LegalCopyright', 'Copyright scrcpy-launcher contributors'),
         StringStruct('Comments', 'Licensed under GPL-3.0-only'),
         StringStruct('OriginalFilename', 'scrcpy-launcher.exe'),
         StringStruct('ProductName', 'scrcpy-launcher'),
         StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
