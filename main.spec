# -*- mode: python ; coding: utf-8 -*-
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files

# Target architecture from the environment; empty lets the system decide
target_arch = os.environ.get('TARGET_ARCH', None)

base_datas = [
    ('webui', 'webui'),
    ('desktop/style.qss', 'desktop'),
    ('desktop/MaterialIcons-Regular.ttf', 'desktop'),
    ('desktop/icon-volume-off.png', 'desktop'),
    ('desktop/icon-volume-up.png', 'desktop'),
    ('desktop/icon.png', 'desktop'),
    ('icon.ico', '.'),
]
if sys.platform == 'win32':
    base_datas.append(('drivers/vbcable.zip', 'drivers'))
    base_datas.append(('virtualcam/poros-cam.dll', 'virtualcam'))

datas, binaries, hiddenimports = [], [], []

# Native extensions and the data they need at runtime (FFmpeg / PortAudio / SRTP)
for package in ('aiortc', 'av', 'sounddevice', 'pylibsrtp', 'aioice', 'google_crc32c', 'pyee'):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

datas += collect_data_files('segno')

hiddenimports += [
    'engineio.async_drivers.threading',
    'engineio.async_drivers.aiohttp',
    'aiohttp',
    'numpy',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=base_datas + datas,  # front-end assets, styles and the driver
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

# Two shapes from one spec:
#   POROS_ONEFILE=1 -> a single portable exe (unpacks the payload into %TEMP%
#                        on every launch, so it starts slower)
#   otherwise         -> the one-dir folder the installer ships, which starts
#                        straight from disk
if os.environ.get('POROS_ONEFILE') == '1':
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='Poros-Portable',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,  # Qt / FFmpeg DLLs do not survive UPX compression
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=target_arch,  # target architecture
        codesign_identity=None,
        entitlements_file=None,
        icon='icon.ico',
        uac_admin=False,  # Windows asks for administrator rights on launch
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='Poros',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,  # Qt / FFmpeg DLLs do not survive UPX compression
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=target_arch,  # target architecture
        codesign_identity=None,
        entitlements_file=None,
        icon='icon.ico',
        uac_admin=False,  # Windows asks for administrator rights on launch
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='Poros',
    )
