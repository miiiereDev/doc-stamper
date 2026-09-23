# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['autostamper.py'],
    pathex=[],
    binaries=[],
    datas=[('README.md', '.'), ('autostamper', 'autostamper')],
    hiddenimports=[
        'fitz', 'pymupdf', 'PIL', 'PIL.Image',
        'shiboken6',
        'autostamper.config', 'autostamper.canvas', 'autostamper.image', 'autostamper.worker', 'autostamper.main_window',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest', 'tests', 'tkinter', 'matplotlib', 'scipy', 'numpy',
        'PySide6.Qt3DAnimation', 'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DExtras', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtGraphs', 'PySide6.QtGraphsWidgets',
        'PySide6.QtLocation', 'PySide6.QtPositioning', 'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineQuick', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
        'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQuick3D', 'PySide6.QtQml', 'PySide6.QtWebChannel', 'PySide6.QtWebSockets',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AutoStamper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
