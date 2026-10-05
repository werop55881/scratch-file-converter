# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_data_files

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
