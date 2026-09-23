# Build Portable EXE

## Prerequisites
- Windows 10/11 64-bit
- Python 3.12 (tested) with `pip`
- MSVC Build Tools not required for PyInstaller (prebuilt bootloader)
- No admin needed to run, admin may be needed to install Python

## Install deps
```powershell
pip install -r requirements.txt
pip install pyinstaller==6.22.3
```

## Build
```powershell
# Single-file (one exe, 70-80 MB, extracts to %TEMP% on start, 3-4s delay)
pyinstaller AutoStamper-OneFile.spec --noconfirm --clean

# Onedir portable folder (faster start, AV friendlier, 170 MB folder)
pyinstaller AutoStamper-Onedir.spec --noconfirm --clean

# Output
# dist/AutoStamper.exe
# dist/AutoStamper-portable/AutoStamper.exe + _internal/
```

Specs are lean: excludes Qt3D/Charts/WebEngine etc via `excludes` — size 71 MB vs 282 MB unoptimized.

## Test portable (zero-install)
```powershell
# copy to USB or temp, run without PYTHONPATH
.\dist\AutoStamper.exe
# or
.\dist\AutoStamper-portable\AutoStamper.exe
# open qa_sample folder, verify stamping -> .stamped/
```

## Create ZIP
```powershell
Compress-Archive -Path dist\AutoStamper.exe -DestinationPath AutoStamper-Portable-SingleFile.zip
Compress-Archive -Path dist\AutoStamper-portable\* -DestinationPath AutoStamper-Portable.zip
```

## Notes
- Windowed (`console=False`) — no console. Use `--console` spec variant for debug.
- UPX disabled (AV false-positive).
- Writes nothing to registry or %APPDATA%; only `.stamped/` beside input.
- Bundles MSVC runtime via PyInstaller.
```

