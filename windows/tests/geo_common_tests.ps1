# geo_common_tests.ps1 - dependency-free assertions for the pure helpers in windows\geo_common.ps1.
# Runs under Windows PowerShell 5.1 and PowerShell 7:
#   powershell -NoProfile -ExecutionPolicy Bypass -File windows\tests\geo_common_tests.ps1
# Exit code 0 when every assertion passes, 1 otherwise.

$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'geo_common.ps1')

$script:Passed = 0
$script:Failed = 0
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('geo common tests ' + [guid]::NewGuid().ToString('N'))
[void][System.IO.Directory]::CreateDirectory($TempRoot)
$script:GeoLogPathOverride = Join-Path $TempRoot 'geo_workbench.log'

function Assert-True {
    param([bool]$Condition, [string]$Name)
    if ($Condition) {
        $script:Passed++
    } else {
        $script:Failed++
        Write-Host ('FAIL: ' + $Name)
    }
}

function Assert-Equal {
    param($Expected, $Actual, [string]$Name)
    if ("$Expected" -ceq "$Actual") {
        $script:Passed++
    } else {
        $script:Failed++
        Write-Host ('FAIL: ' + $Name + ' expected [' + $Expected + '] got [' + $Actual + ']')
    }
}

function Test-Throws {
    param([scriptblock]$Block)
    try { & $Block | Out-Null } catch { return $true }
    return $false
}

$sCedilla = [char]0x015F
$uUmlaut = [char]0x00FC
$IDot = [char]0x0130

try {
    # ---- quoting
    Assert-Equal 'plain' (ConvertTo-QuotedArg 'plain') 'quote: plain argument unchanged'
    Assert-Equal '""' (ConvertTo-QuotedArg '') 'quote: empty argument'
    Assert-Equal '"a b"' (ConvertTo-QuotedArg 'a b') 'quote: space'
    Assert-Equal '"C:\Program Files\x\\"' (ConvertTo-QuotedArg 'C:\Program Files\x\') 'quote: trailing backslash doubled'
    Assert-Equal 'C:\dir\file' (ConvertTo-QuotedArg 'C:\dir\file') 'quote: inner backslashes kept'
    Assert-Equal '"say \"hi\""' (ConvertTo-QuotedArg 'say "hi"') 'quote: embedded quotes'
    Assert-Equal '"a\\\"b"' (ConvertTo-QuotedArg 'a\"b') 'quote: backslash before quote'
    $nonAscii = 'C:\Users\' + $sCedilla + $uUmlaut + 'kr' + $uUmlaut + ' Y\GEO paket'
    Assert-Equal ('"' + $nonAscii + '"') (ConvertTo-QuotedArg $nonAscii) 'quote: non-ASCII path with space'
    Assert-Equal ('-d Ubuntu-24.04 --cd "/home/a b" --exec /usr/bin/python3 ""') `
        (ConvertTo-ProcessArgString -ArgumentList @('-d', 'Ubuntu-24.04', '--cd', '/home/a b', '--exec', '/usr/bin/python3', '')) `
        'quote: argument string'
    Assert-Equal '' (ConvertTo-ProcessArgString -ArgumentList @()) 'quote: empty argument list'

    # ---- WSL argv
    $argv = New-WslArgv -Distro 'Ubuntu' -Cd '/home/u/geo-workbench-src' -Exec '/home/u/geo-workbench-src/.venv/bin/python' -Arguments @('dashboard/geo_pilot.py', 'status', '--json')
    Assert-Equal '-d|Ubuntu|--cd|/home/u/geo-workbench-src|--exec|/home/u/geo-workbench-src/.venv/bin/python|dashboard/geo_pilot.py|status|--json' ($argv -join '|') 'argv: order'
    $argv = New-WslArgv -Distro 'Ubuntu' -Exec 'pwd'
    Assert-Equal '-d|Ubuntu|--exec|pwd' ($argv -join '|') 'argv: minimal'
    Assert-True (Test-Throws { New-WslArgv -Distro 'Ubuntu' -Exec 'python3' -Arguments @('a"b') }) 'argv: double quote rejected'
    Assert-True (Test-Throws { New-WslArgv -Distro 'Ubuntu' -Exec 'python3' -Arguments @('ok', '') }) 'argv: empty argument rejected'

    # ---- exit code messages
    foreach ($code in @(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 20, 21, 22, 23, 24, 30, 31, 32, 33, 34, 40, 41)) {
        $message = Get-PilotMessage -Code $code
        Assert-True ($message.Length -gt 0 -and $message -notlike 'Bilinmeyen cikis kodu*') ('message: code ' + $code + ' mapped')
        Assert-True ($message -cmatch '^[\x20-\x7E]+$') ('message: code ' + $code + ' is printable ASCII')
    }
    Assert-True ((Get-PilotMessage -Code 99) -like 'Bilinmeyen cikis kodu: 99*') 'message: unknown code'
    Assert-True ((Get-PilotMessage -Code 3 -Action 'stop-pilot') -ne (Get-PilotMessage -Code 3 -Action 'pilot')) 'message: code 3 depends on action'
    Assert-True ((Get-PilotMessage -Code 0 -Action 'pilot') -like '*benchmark degildir*') 'message: pilot is not a benchmark'

    # ---- VERSION.json
    $pkg = Join-Path $TempRoot ('paket ' + $sCedilla)
    [void][System.IO.Directory]::CreateDirectory($pkg)
    Assert-True ($null -eq (Read-PackageVersion -Root $pkg)) 'version: missing file'
    $commit = 'a' * 40
    $digest = 'b' * 64
    $json = '{"version": "0.1.0-win.7", "commit": "' + $commit + '", "source_manifest_sha256": "' + $digest + '"}'
    [System.IO.File]::WriteAllText((Join-Path $pkg 'VERSION.json'), $json, (New-Object System.Text.UTF8Encoding($false)))
    $version = Read-PackageVersion -Root $pkg
    Assert-Equal $commit $version.Commit 'version: commit'
    Assert-Equal $digest $version.ManifestSha256 'version: manifest digest'
    Assert-Equal '0.1.0-win.7' $version.Version 'version: version'
    [System.IO.File]::WriteAllText((Join-Path $pkg 'VERSION.json'), '{"version": "x", "commit": "not-a-sha"}', (New-Object System.Text.UTF8Encoding($false)))
    $version = Read-PackageVersion -Root $pkg
    Assert-True ($null -eq $version.Commit -and $null -eq $version.ManifestSha256) 'version: invalid fields are null'
    [System.IO.File]::WriteAllText((Join-Path $pkg 'VERSION.json'), '{not json', (New-Object System.Text.UTF8Encoding($false)))
    Assert-True ($null -eq (Read-PackageVersion -Root $pkg)) 'version: corrupt file'

    # ---- wsl -l -v parsing
    $nul = [string][char]0
    $sample = "  NAME            STATE           VERSION`r`n* Ubuntu-24.04    Running         2`r`n  Debian          Stopped         1`r`n  docker-desktop  Stopped         2`r`n"
    $utf16Like = [string][char]0xFEFF + (($sample.ToCharArray() | ForEach-Object { [string]$_ + $nul }) -join '')
    foreach ($text in @($sample, $utf16Like)) {
        $distros = @(ConvertFrom-WslListText -Text $text)
        Assert-Equal 3 $distros.Count 'wsl list: count'
        Assert-Equal 'Ubuntu-24.04' $distros[0].Name 'wsl list: default name'
        Assert-True ($distros[0].Default) 'wsl list: default marker'
        Assert-Equal 2 $distros[0].Version 'wsl list: version 2'
        Assert-Equal 'Running' $distros[0].State 'wsl list: state'
        Assert-Equal 'Debian' $distros[1].Name 'wsl list: second name'
        Assert-True (-not $distros[1].Default) 'wsl list: no default marker'
        Assert-Equal 1 $distros[1].Version 'wsl list: version 1'
    }
    $localized = "  AD              DURUM           S" + $uUmlaut + "R" + $uUmlaut + "M`n* Ubuntu          " + [char]0x00C7 + "al" + [char]0x0131 + $sCedilla + [char]0x0131 + "yor  2`n"
    $distros = @(ConvertFrom-WslListText -Text $localized)
    Assert-Equal 1 $distros.Count 'wsl list: localized header'
    Assert-Equal 'Ubuntu' $distros[0].Name 'wsl list: localized name'
    $none = "Windows Subsystem for Linux has no installed distributions.`r`nYou can resolve this by installing a distribution with the instructions below:`r`n`r`nUse 'wsl.exe --list --online' to list available distributions`r`nand 'wsl.exe --install <Distro>' to install.`r`n"
    Assert-Equal 0 (@(ConvertFrom-WslListText -Text $none)).Count 'wsl list: no distributions message'
    Assert-Equal 0 (@(ConvertFrom-WslListText -Text '')).Count 'wsl list: empty text'

    # ---- geo_pilot JSON lines
    $parsed = ConvertFrom-PilotJson ("noise line`n" + '{"found": true, "job_id": "job-1", "state": "running"}')
    Assert-Equal 'job-1' $parsed.job_id 'pilot json: last JSON line'
    Assert-True ($parsed.found) 'pilot json: boolean'
    Assert-True ($null -eq (ConvertFrom-PilotJson 'Traceback (most recent call last):')) 'pilot json: no JSON'
    Assert-True ($null -eq (ConvertFrom-PilotJson '{broken')) 'pilot json: broken JSON'
    Assert-True ($null -eq (ConvertFrom-PilotJson '')) 'pilot json: empty'

    # ---- backend state round trip
    $statePath = Join-Path (Join-Path $TempRoot ('state ' + $IDot)) 'wsl_backend.json'
    Assert-True ($null -eq (Read-BackendState -Path $statePath)) 'state: missing file'
    $state = [ordered]@{
        schema          = 'GEO-workbench-wsl-backend/1'
        distro          = 'Ubuntu-24.04'
        src             = '/home/user/geo-workbench-src'
        python          = '/home/user/geo-workbench-src/.venv/bin/python'
        commit          = $commit
        manifest_sha256 = $digest
        package_root    = $nonAscii
        configured_at   = '2026-11-05T00:00:00Z'
    }
    Write-BackendState -State $state -Path $statePath
    $back = Read-BackendState -Path $statePath
    Assert-True ($null -ne $back) 'state: read back'
    Assert-Equal 'Ubuntu-24.04' $back.distro 'state: distro'
    Assert-Equal '/home/user/geo-workbench-src' $back.src 'state: src'
    Assert-Equal $nonAscii $back.package_root 'state: non-ASCII package root'
    Write-BackendState -State $state -Path $statePath
    Assert-True ($null -ne (Read-BackendState -Path $statePath)) 'state: overwrite'
    $bad = [ordered]@{}
    foreach ($k in $state.Keys) { $bad[$k] = $state[$k] }
    $bad['src'] = '/mnt/c/Users/x/geo-workbench-src'
    $bad['python'] = '/mnt/c/Users/x/geo-workbench-src/.venv/bin/python'
    Write-BackendState -State $bad -Path $statePath
    Assert-True ($null -eq (Read-BackendState -Path $statePath)) 'state: source under /mnt refused'
    $bad['src'] = $state['src']
    $bad['python'] = $state['python']
    $bad['schema'] = 'other/1'
    Write-BackendState -State $bad -Path $statePath
    Assert-True ($null -eq (Read-BackendState -Path $statePath)) 'state: wrong schema refused'
    [System.IO.File]::WriteAllText($statePath, '{oops', (New-Object System.Text.UTF8Encoding($false)))
    Assert-True ($null -eq (Read-BackendState -Path $statePath)) 'state: corrupt file'

    # ---- pid records
    $pidPath = Join-Path $TempRoot 'geo_ui.pid'
    Write-PidRecord -Path $pidPath -ProcessId 1234 -Port 8531 -Engine 'wsl2'
    $record = Read-PidRecord -Path $pidPath
    Assert-Equal 1234 $record.ProcessId 'pid: process id'
    Assert-Equal 8531 $record.Port 'pid: port'
    Assert-Equal 'wsl2' $record.Engine 'pid: engine'
    [System.IO.File]::WriteAllText($pidPath, 'garbage')
    Assert-True ($null -eq (Read-PidRecord -Path $pidPath)) 'pid: corrupt record'

    # ---- port check
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $busyPort = $listener.LocalEndpoint.Port
    Assert-True (-not (Test-PortFree -Port $busyPort)) 'port: busy port detected'
    $listener.Stop()
    Assert-True (Test-PortFree -Port $busyPort) 'port: freed port is free'

    # ---- log
    Write-GeoLog 'INFO' ('test ' + $sCedilla)
    Assert-True ([System.IO.File]::Exists($script:GeoLogPathOverride)) 'log: written'
} catch {
    $script:Failed++
    Write-Host ('FAIL: unexpected exception: ' + $_.Exception.Message)
    Write-Host ($_.ScriptStackTrace)
} finally {
    try { [System.IO.Directory]::Delete($TempRoot, $true) } catch { }
}

Write-Host ('geo_common_tests: {0} passed, {1} failed (PowerShell {2})' -f $script:Passed, $script:Failed, $PSVersionTable.PSVersion)
if ($script:Failed -gt 0) { exit 1 }
exit 0
