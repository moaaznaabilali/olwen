# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['olwen_app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['pyobjc', 'AppKit', 'Foundation', 'PyObjCTools.AppHelper', 'WebKit', 'ApplicationServices', 'Quartz'],
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
    name='Olwen',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources/Olwen.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Olwen',
)
app = BUNDLE(
    coll,
    name='Olwen.app',
    icon='resources/Olwen.icns',
    bundle_identifier='com.olwen.app',
)
