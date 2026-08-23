# SPDX-License-Identifier: GPL-3.0-only

from pathlib import Path

project_root = Path(SPECPATH).parent
icon_path = project_root / "icon.ico"
version_path = project_root / "build" / "version_info.txt"

a = Analysis(
    [str(project_root / "scrcpy_launcher.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[(str(icon_path), ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="scrcpy-launcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path),
    version=str(version_path),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="scrcpy-launcher",
)
