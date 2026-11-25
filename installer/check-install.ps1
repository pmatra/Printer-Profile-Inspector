param([Parameter(Mandatory=$true)][string]$Installer, [string]$TestRoot = '', [switch]$VerifyPreservedShortcuts, [switch]$TestShortcuts)
$ErrorActionPreference = 'Stop'
$Installer = (Resolve-Path -LiteralPath $Installer).Path
if (-not $TestRoot) { $TestRoot = Join-Path ([IO.Path]::GetTempPath()) ('ICC-Installer-Test-'+[Guid]::NewGuid().ToString('N')) }
if (Test-Path -LiteralPath $TestRoot) { throw 'The installer smoke-test directory must not already exist.' }
New-Item -ItemType Directory -Path $testRoot | Out-Null
$target = Join-Path $testRoot 'Application'
$installLog = Join-Path $testRoot 'install.log'
$report = Join-Path $testRoot 'packaged-check.json'
$shortcutPaths = @((Join-Path ([Environment]::GetFolderPath('Programs')) 'ICC Profile Inspector.lnk'), (Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'ICC Profile Inspector.lnk'))
$sentinels = @()
if ($VerifyPreservedShortcuts -or $TestShortcuts) {
    foreach ($link in $shortcutPaths) {
        if (Test-Path -LiteralPath $link) { throw "Refusing to overwrite an existing shortcut during a test: $link" }
        if ($VerifyPreservedShortcuts) {
            New-Item -ItemType Directory -Force -Path (Split-Path $link -Parent) | Out-Null
            [IO.File]::WriteAllText($link, 'Installer ownership regression sentinel')
            $sentinels += $link
        }
    }
}
$iconChoice = if ($TestShortcuts) { '1' } else { '0' }
try {
    $process = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER',('/STARTMENU='+$iconChoice),('/DESKTOP='+$iconChoice),('/DIR="'+$target+'"'),('/LOG="'+$installLog+'"')) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed ($($process.ExitCode)); log: $installLog" }
    $app = Join-Path $target 'ICC Gamut Inspector.exe'
    if (-not (Test-Path -LiteralPath $app)) { throw 'Installed executable is missing.' }
    $process = Start-Process -FilePath $app -ArgumentList @('--platform-check',('"'+$report+'"')) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $report)) { throw 'Installed app smoke check failed.' }
    $result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if (-not $result.passed) { throw "Installed application checks failed: $($result.error)" }
    if ($TestShortcuts) {
        $ownership = Join-Path $target 'installer-shortcuts.ini'
        if (-not (Test-Path -LiteralPath $ownership)) { throw 'Shortcut ownership was not recorded.' }
        $shell = New-Object -ComObject WScript.Shell
        foreach ($link in $shortcutPaths) {
            if (-not (Test-Path -LiteralPath $link)) { throw 'Selected shortcut was not created.' }
            if ($shell.CreateShortcut($link).TargetPath -ne $app) { throw 'Shortcut points at the wrong executable.' }
        }
    }
    Write-Output 'Installed executable and native platform checks passed.'
} catch {
    if (Test-Path -LiteralPath $installLog) { Get-Content -LiteralPath $installLog -Tail 35 | Write-Output }
    throw
} finally {
    $uninstaller = Join-Path $target 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        $process = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -WindowStyle Hidden -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw 'Test uninstallation failed.' }
        if (Test-Path -LiteralPath (Join-Path $target 'ICC Gamut Inspector.exe')) { throw 'Test application was not removed.' }
        Write-Output 'Uninstallation passed; no user profiles or preferences were removed.'
    }
    if ($TestShortcuts) {
        foreach ($link in $shortcutPaths) { if (Test-Path -LiteralPath $link) { throw 'Installer-owned shortcut remained after uninstall.' } }
        Write-Output 'Selected Start menu and Desktop shortcuts pointed at the installed app and were removed on uninstall.'
    }
    foreach ($link in $sentinels) {
        if (-not (Test-Path -LiteralPath $link) -or [IO.File]::ReadAllText($link) -ne 'Installer ownership regression sentinel') { throw 'An unowned shortcut was changed or removed.' }
        Remove-Item -LiteralPath $link
    }
    if ($sentinels.Count) { Write-Output 'Pre-existing unowned shortcuts were preserved.' }
}
