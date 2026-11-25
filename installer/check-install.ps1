param([Parameter(Mandatory=$true)][string]$Installer)
$ErrorActionPreference = 'Stop'
$Installer = (Resolve-Path -LiteralPath $Installer).Path
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('ICC-Installer-Test-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$target = Join-Path $testRoot 'Application'
$installLog = Join-Path $testRoot 'install.log'
$report = Join-Path $testRoot 'packaged-check.json'
try {
    $process = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/STARTMENU=0','/DESKTOP=0',('/DIR="'+$target+'"'),('/LOG="'+$installLog+'"')) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed ($($process.ExitCode)); log: $installLog" }
    $app = Join-Path $target 'ICC Gamut Inspector.exe'
    if (-not (Test-Path -LiteralPath $app)) { throw 'Installed executable is missing.' }
    $process = Start-Process -FilePath $app -ArgumentList @('--platform-check',('"'+$report+'"')) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $report)) { throw 'Installed app smoke check failed.' }
    $result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if (-not $result.passed) { throw "Installed application checks failed: $($result.error)" }
    Write-Output 'Installed executable and native platform checks passed.'
} finally {
    $uninstaller = Join-Path $target 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        $process = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -WindowStyle Hidden -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw 'Test uninstallation failed.' }
        if (Test-Path -LiteralPath (Join-Path $target 'ICC Gamut Inspector.exe')) { throw 'Test application was not removed.' }
        Write-Output 'Uninstallation passed; no user profiles or preferences were removed.'
    }
}
