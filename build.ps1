$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    python -m PyInstaller --noconfirm --windowed --onedir --collect-submodules OpenGL.arrays --hidden-import OpenGL.platform.win32 --hidden-import pyopengltk.win32 --name 'ICC Gamut Inspector' inspector.py
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
} finally {
    Pop-Location
}
