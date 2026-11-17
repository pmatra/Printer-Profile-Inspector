$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    python -m PyInstaller --noconfirm --windowed --onedir --name 'ICC Gamut Inspector' inspector.py
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
} finally {
    Pop-Location
}
