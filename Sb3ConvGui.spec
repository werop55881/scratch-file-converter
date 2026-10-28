# -*- mode: python ; coding: utf-8 -*-

import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

# the version resource is generated from sb3conv.__version__ so a release
# bump only touches pyproject.toml + sb3conv/__init__.py
_version = re.search(
    r'__version__ = "([^"]+)"', Path("sb3conv/__init__.py").read_text(encoding="utf-8")
).group(1)
_numbers = (_version.split(".") + ["0", "0", "0"])[:3]
_filevers = "(" + ", ".join(_numbers) + ", 0)"
_version4 = ".".join([*_numbers, "0"])
Path("version_info.txt").write_text(
    f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={_filevers},
    prodvers={_filevers},
    mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [StringTable('040904B0', [
        StringStruct('CompanyName', 'Scratch File Converter contributors'),
        StringStruct('FileDescription', 'Scratch File Converter GUI'),
        StringStruct('FileVersion', '{_version4}'),
        StringStruct('InternalName', 'sb3conv-gui'),
        StringStruct('OriginalFilename', 'sb3conv-gui.exe'),
        StringStruct('ProductName', 'Scratch File Converter'),
        StringStruct('ProductVersion', '{_version4}'),
      ])]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ]
)
""",
    encoding="utf-8",
)

resvg_datas, resvg_binaries, resvg_hidden = collect_all('resvg_py')

a = Analysis(
    ['sb3conv_gui.py'],
    pathex=[],
    binaries=[*resvg_binaries],
    datas=[
        ('sb3conv/backends/python/runtime_src.py', 'sb3conv/backends/python'),
        ('sb3conv/backends/javascript/runtime_src.js', 'sb3conv/backends/javascript'),
        ('sb3conv/backends/c/runtime_src.h', 'sb3conv/backends/c'),
        ('sb3conv/backends/c/runtime_src.c', 'sb3conv/backends/c'),
        ('sb3conv/backends/lua/runtime_src.lua', 'sb3conv/backends/lua'),
        ('sb3conv/backends/godot/runtime_src.gd', 'sb3conv/backends/godot'),
        ('sb3conv/backends/godot/scratch.gd', 'sb3conv/backends/godot'),
        ('sb3conv/backends/c/vendor/nanosvg/nanosvg.h', 'sb3conv/backends/c/vendor/nanosvg'),
        ('sb3conv/backends/c/vendor/nanosvg/nanosvgrast.h', 'sb3conv/backends/c/vendor/nanosvg'),
        ('sb3conv/backends/c/vendor/nanosvg/LICENSE.txt', 'sb3conv/backends/c/vendor/nanosvg'),
        *collect_data_files('sv_ttk'),
        *resvg_datas,
    ],
    hiddenimports=[*resvg_hidden],
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
    a.binaries,
    a.datas,
    [],
    name='sb3conv-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
)
