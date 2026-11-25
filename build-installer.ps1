param(
    [string]$Compiler = '',
    [switch]$SkipAppBuild
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not $SkipAppBuild) {
        & (Join-Path $PSScriptRoot 'build.ps1')
    }
    if (-not $Compiler) {
        $candidate = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($candidate) { $Compiler = $candidate.Source }
        foreach ($path in @("${env:ProgramFiles}\Inno Setup 7\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")) {
            if (-not $Compiler -and (Test-Path -LiteralPath $path)) { $Compiler = $path }
        }
    }
    if (-not $Compiler -or -not (Test-Path -LiteralPath $Compiler)) {
        throw 'Install Inno Setup 7, or pass -Compiler with the path to ISCC.exe.'
    }
    $appVersion = python -c 'from version import __version__; print(__version__)'
    if ($LASTEXITCODE -ne 0) { throw 'Version lookup failed.' }
    & $Compiler "/DAppVersion=$appVersion" (Join-Path $PSScriptRoot 'installer\windows.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
} finally {
    Pop-Location
}
