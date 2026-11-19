$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    python make_version_info.py build/version_info.txt
    if ($LASTEXITCODE -ne 0) { throw 'Version metadata generation failed.' }
    python -m PyInstaller --noconfirm --windowed --onedir --version-file build/version_info.txt --collect-submodules OpenGL.arrays --hidden-import OpenGL.platform.win32 --hidden-import pyopengltk.win32 --hidden-import send2trash.win.modern --hidden-import win32com.shell.shell --hidden-import win32com.shell.shellcon --name 'ICC Gamut Inspector' inspector.py
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
    foreach ($notice in @('LICENSE', 'THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_LICENSES.txt')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $notice) -Destination (Join-Path $PSScriptRoot 'dist\ICC Gamut Inspector')
    }
} finally {
    Pop-Location
}
