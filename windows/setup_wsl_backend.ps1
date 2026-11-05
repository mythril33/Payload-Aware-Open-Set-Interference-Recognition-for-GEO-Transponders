# setup_wsl_backend.ps1 - consent-gated, one-time WSL2 setup for the one-click GEO pilot.
#
# Steps (each one explained and logged; nothing is installed without an explicit [E/H] answer):
#   1. read VERSION.json / SOURCE_MANIFEST.json of this CI package (a Git checkout cannot be used)
#   2. find wsl.exe and an Ubuntu distribution; without one, offer `wsl --install -d Ubuntu-24.04`
#      (enabling WSL itself needs administrator approval through UAC and possibly a reboot)
#   3. check WSL2 and python3 >= 3.10 inside the distribution
#   4. copy the verified package source into the WSL ext4 home (~/geo-workbench-src) with
#      windows/wsl/geo_wsl_setup.py install; an existing different copy is moved aside, never deleted
#   5. create ~/geo-workbench-src/.venv and install the CPU dependencies (geo_wsl_setup.py venv)
#   6. run geo_pilot.py preflight against this package's commit and manifest digest
#   7. only then write %LOCALAPPDATA%\GEO-Workbench\wsl_backend.json
#
# Exit codes are listed in geo_common.ps1. Log: windows\logs\geo_workbench.log.

param(
    [string]$WslExe = '',
    [string]$Distro = ''
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
. (Join-Path $PSScriptRoot 'geo_common.ps1')

$DefaultDistro = 'Ubuntu-24.04'
$RepoRoot = Get-RepoRoot

function Install-WslWithConsent {
    param([string]$WslPath, [bool]$Elevate)
    Write-Host ''
    Write-GeoInfo ('Bu bilgisayarda kullanilabilir bir Ubuntu WSL dagitimi yok. Kurulum komutu: wsl --install -d ' + $DefaultDistro)
    if ($Elevate) {
        Write-GeoInfo 'WSL ozelligi henuz etkin degil: Windows bir yonetici onayi (UAC penceresi) isteyecek ve'
        Write-GeoInfo 'kurulumdan sonra bilgisayari yeniden baslatmaniz gerekebilir.'
    } else {
        Write-GeoInfo 'Yeni bir pencerede Ubuntu kurulur ve sizden bir Linux kullanici adi ile parola olusturmaniz istenir.'
    }
    Write-GeoInfo 'Ubuntu, Microsoft kaynaklarindan indirilir (birkac yuz MB).'
    $answer = ''
    try { $answer = Read-Host 'WSL/Ubuntu kurulumu simdi baslatilsin mi? [E/H]' } catch { $answer = '' }
    if ("$answer".Trim() -notmatch '^[Ee]') {
        Write-GeoInfo (Get-PilotMessage 5)
        return 5
    }
    $argString = ConvertTo-ProcessArgString -ArgumentList @('--install', '-d', $DefaultDistro)
    Write-GeoLog 'INFO' ('wsl.exe ' + $argString + ' (elevate=' + $Elevate + ')')
    try {
        if ($Elevate) {
            $proc = Start-Process -FilePath $WslPath -ArgumentList $argString -Verb RunAs -PassThru -Wait
        } else {
            $proc = Start-Process -FilePath $WslPath -ArgumentList $argString -PassThru -Wait
        }
    } catch {
        Write-GeoErr ('Kurulum baslatilamadi veya yonetici onayi verilmedi: ' + $_.Exception.Message)
        return 5
    }
    Write-GeoLog 'INFO' ('wsl --install exit ' + $proc.ExitCode)
    Write-GeoOk (Get-PilotMessage 7)
    return 7
}

function Select-UbuntuDistro {
    param($Distros, [string]$Preferred)
    $all = @($Distros)
    if ($Preferred) { return @($all | Where-Object { $_.Name -eq $Preferred }) | Select-Object -First 1 }
    $state = Read-BackendState
    if ($null -ne $state) {
        $previous = @($all | Where-Object { $_.Name -eq "$($state.distro)" }) | Select-Object -First 1
        if ($null -ne $previous) { return $previous }
    }
    $ubuntu = @($all | Where-Object { $_.Name -like 'Ubuntu*' })
    $default = @($ubuntu | Where-Object { $_.Default }) | Select-Object -First 1
    if ($null -ne $default) { return $default }
    return ($ubuntu | Select-Object -First 1)
}

function Get-PythonVersionOk {
    param([string]$WslPath, [string]$Name)
    $r = Invoke-WslExec -WslExe $WslPath -Distro $Name -Cd '~' -Exec 'python3' -Arguments @('--version')
    if ($r.ExitCode -ne 0 -or $r.Stdout -notmatch 'Python (\d+)\.(\d+)') { return $null }
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    return [pscustomobject]@{ Text = ('{0}.{1}' -f $major, $minor); Ok = ($major -eq 3 -and $minor -ge 10) }
}

function Install-VenvPackageWithConsent {
    param([string]$WslPath, [string]$Name)
    Write-GeoWarn (Get-PilotMessage 15)
    Write-GeoInfo 'Yeni bir pencerede "sudo apt-get install -y python3-venv" calistirilir; Ubuntu kendi parolanizi sorabilir.'
    if (-not (Read-Consent 'python3-venv simdi kurulsun mu?')) { return $false }
    foreach ($step in @(@('sudo', 'apt-get', 'install', '-y', 'python3-venv'),
                        @('sudo', 'apt-get', 'update'),
                        @('sudo', 'apt-get', 'install', '-y', 'python3-venv'))) {
        $argv = New-WslArgv -Distro $Name -Cd '~' -Exec ($step[0]) -Arguments ($step[1..($step.Count - 1)])
        $argString = ConvertTo-ProcessArgString -ArgumentList $argv
        Write-GeoLog 'INFO' ('visible: wsl.exe ' + $argString)
        try {
            $proc = Start-Process -FilePath $WslPath -ArgumentList $argString -PassThru -Wait
        } catch {
            Write-GeoErr ('Pencere acilamadi: ' + $_.Exception.Message)
            return $false
        }
        Write-GeoLog 'INFO' ('exit ' + $proc.ExitCode)
        if ($proc.ExitCode -eq 0 -and $step[-1] -eq 'python3-venv') { return $true }
    }
    return $false
}

function Invoke-Setup {
    Write-Host '====================================================='
    Write-Host ' GEO WSL Kurulumu - gercek RF pilotu icin WSL2 arka ucu'
    Write-Host '====================================================='
    Write-GeoInfo 'Bu kurulum bir kez yapilir ve sunlari yapar:'
    Write-GeoInfo ' - bu paketin dogrulanmis kaynak kopyasini WSL2 Ubuntu ev dizinine (~/geo-workbench-src) kopyalar,'
    Write-GeoInfo ' - orada bir Python sanal ortami kurar (PyTorch CPU dahil, birkac GB indirme),'
    Write-GeoInfo ' - pilot on kontrolunu calistirir ve sonucu %LOCALAPPDATA%\GEO-Workbench altina kaydeder.'
    Write-GeoInfo 'Gerekirse WSL/Ubuntu kurulumu ve python3-venv paketi icin ayrica onay istenir.'
    Write-GeoInfo 'Hicbir uretim, GPU veya held-out kapisi acilmaz; pilot 21.350 gozlemlik benchmark degildir.'
    Write-Host ''
    if (-not (Read-Consent 'Devam edilsin mi?')) {
        Write-GeoInfo (Get-PilotMessage 5)
        return 5
    }

    Write-Host '--- 1/6 Paket ---'
    $version = Read-PackageVersion -Root $RepoRoot
    $setupPy = Join-Path (Join-Path (Join-Path $RepoRoot 'windows') 'wsl') 'geo_wsl_setup.py'
    $manifest = Join-Path $RepoRoot 'SOURCE_MANIFEST.json'
    if ($null -eq $version -or -not $version.Commit -or -not $version.ManifestSha256 -or
        -not (Test-Path -LiteralPath $manifest -PathType Leaf) -or -not (Test-Path -LiteralPath $setupPy -PathType Leaf)) {
        Write-GeoErr (Get-PilotMessage 9)
        return 9
    }
    Write-GeoOk ('Paket surumu ' + $version.Version + ', commit ' + $version.Commit)

    Write-Host '--- 2/6 WSL ---'
    $wsl = Find-WslExe -WslExe $WslExe
    if (-not $wsl) {
        Write-GeoErr 'wsl.exe bulunamadi. WSL, Windows 10 surum 2004 (derleme 19041) veya Windows 11 gerektirir.'
        Write-GeoErr 'Windows Update ile sisteminizi guncelleyip bu kisayolu yeniden calistirin.'
        return 3
    }
    $distros = @(Get-WslDistros -WslExe $wsl)
    $chosen = Select-UbuntuDistro -Distros $distros -Preferred $Distro
    if ($null -eq $chosen) {
        if ($Distro) {
            Write-GeoErr ('Istenen dagitim bulunamadi: ' + $Distro)
            return 3
        }
        $elevate = -not (Test-WslStatus -WslExe $wsl)
        return (Install-WslWithConsent -WslPath $wsl -Elevate $elevate)
    }
    $name = $chosen.Name
    if ($chosen.Version -ne 2) {
        Write-GeoErr ('Dagitim ' + $name + ' WSL1 olarak kurulu. Pilot WSL2 gerektirir.')
        Write-GeoErr ('Donusturmek icin bir komut isteminde: wsl --set-version ' + $name + ' 2   (sonra bu kisayolu yeniden calistirin)')
        return 8
    }
    Write-GeoOk ('Dagitim: ' + $name + ' (WSL2)')

    Write-Host '--- 3/6 Python ---'
    $py = Get-PythonVersionOk -WslPath $wsl -Name $name
    if ($null -eq $py -or -not $py.Ok) {
        Write-GeoErr (Get-PilotMessage 8)
        Write-GeoErr ('Ubuntu icinde python3 kurun (sudo apt-get install -y python3) ve bu kisayolu yeniden calistirin.')
        return 8
    }
    Write-GeoOk ('python3 ' + $py.Text)
    $pkgWsl = (Invoke-WslExec -WslExe $wsl -Distro $name -Cd '~' -Exec 'wslpath' -Arguments @('-a', $RepoRoot))
    $homeWsl = (Invoke-WslExec -WslExe $wsl -Distro $name -Cd '~' -Exec 'pwd')
    $pkgPath = "$($pkgWsl.Stdout)".Trim()
    $homePath = "$($homeWsl.Stdout)".Trim()
    if ($pkgWsl.ExitCode -ne 0 -or $pkgPath -notmatch '^/' -or $homeWsl.ExitCode -ne 0 -or $homePath -notmatch '^/' -or $homePath -match '^/mnt(/|$)') {
        Write-GeoErr ('WSL yollari belirlenemedi (wslpath: ' + $pkgPath + ', ev dizini: ' + $homePath + ').')
        return 1
    }
    $dest = $homePath.TrimEnd('/') + '/geo-workbench-src'
    $pkgSetup = $pkgPath.TrimEnd('/') + '/windows/wsl/geo_wsl_setup.py'

    Write-Host '--- 4/6 Kaynak kopyasi ---'
    Write-GeoInfo ('Paket (Windows): ' + $RepoRoot)
    Write-GeoInfo ('Hedef (WSL ext4): ' + $dest)
    $install = Invoke-WslExec -WslExe $wsl -Distro $name -Cd '~' -Exec 'python3' -Arguments @($pkgSetup, 'install', '--from', $pkgPath, '--to', $dest, '--json')
    $result = ConvertFrom-PilotJson $install.Stdout
    $reused = $false
    if ($install.ExitCode -eq 13 -and $null -ne $result) {
        if ("$($result.existing_commit)" -eq $version.Commit -and $result.existing_verified) {
            Write-GeoOk 'WSL icinde ayni commit ile dogrulanmis bir kopya zaten var; yeniden kullaniliyor.'
            $reused = $true
        } else {
            Write-GeoWarn ('WSL icinde baska bir kopya var (commit ' + $result.existing_commit + ', dogrulanmis: ' + $result.existing_verified + ').')
            Write-GeoWarn 'Mevcut kopya silinmez; ".previous-<zaman>" ekiyle kenara tasinir. Calisan bir pilot varsa once onu bitirin.'
            $oldPython = $dest + '/.venv/bin/python'
            $old = Invoke-WslExec -WslExe $wsl -Distro $name -Cd '~' -Exec 'test' -Arguments @('-x', $oldPython)
            if ($old.ExitCode -eq 0) {
                $oldStatus = ConvertFrom-PilotJson (Invoke-WslExec -WslExe $wsl -Distro $name -Cd $dest -Exec $oldPython -Arguments @($dest + '/dashboard/geo_pilot.py', 'status', '--json')).Stdout
                if ($null -ne $oldStatus -and $oldStatus.found -and "$($oldStatus.state)" -eq 'running') {
                    Write-GeoErr ('Mevcut kopyada bir pilot calisiyor (JOB_ID=' + $oldStatus.job_id + '); kopya degistirilmedi.')
                    return 10
                }
            }
            if (-not (Read-Consent 'Yeni surum kurulsun ve eski kopya kenara tasinsin mi?')) {
                Write-GeoInfo (Get-PilotMessage 5)
                return 5
            }
            $install = Invoke-WslExec -WslExe $wsl -Distro $name -Cd '~' -Exec 'python3' -Arguments @($pkgSetup, 'install', '--from', $pkgPath, '--to', $dest, '--replace', '--json')
            $result = ConvertFrom-PilotJson $install.Stdout
        }
    }
    if ($install.ExitCode -ne 0 -and -not $reused) {
        Write-GeoErr (Get-PilotMessage $install.ExitCode)
        if ($null -ne $result -and $result.message) { Write-GeoInfo ('geo_wsl_setup: ' + $result.message) }
        return $install.ExitCode
    }
    if (-not $reused) {
        Write-GeoOk ('Kaynak kopyalandi ve dogrulandi: ' + $dest)
        if ($null -ne $result -and $result.previous) { Write-GeoInfo ('Eski kopya: ' + $result.previous) }
    }

    Write-Host '--- 5/6 Sanal ortam (uzun surebilir) ---'
    $destSetup = $dest + '/windows/wsl/geo_wsl_setup.py'
    $venv = Invoke-WslExec -WslExe $wsl -Distro $name -Cd '~' -Exec 'python3' -Arguments @($destSetup, 'venv', '--src', $dest, '--json')
    if ($venv.ExitCode -eq 15) {
        if (-not (Install-VenvPackageWithConsent -WslPath $wsl -Name $name)) {
            Write-GeoErr (Get-PilotMessage 15)
            return 15
        }
        $venv = Invoke-WslExec -WslExe $wsl -Distro $name -Cd '~' -Exec 'python3' -Arguments @($destSetup, 'venv', '--src', $dest, '--json')
    }
    if ($venv.ExitCode -eq 2) {
        Write-GeoErr (Get-PilotMessage 8)
        return 8
    }
    if ($venv.ExitCode -ne 0) {
        Write-GeoErr (Get-PilotMessage $venv.ExitCode)
        $v = ConvertFrom-PilotJson $venv.Stdout
        if ($null -ne $v -and $v.message) { Write-GeoInfo ('geo_wsl_setup: ' + $v.message) }
        return $venv.ExitCode
    }
    Write-GeoOk 'Sanal ortam hazir.'

    Write-Host '--- 6/6 Pilot on kontrolu ---'
    $python = $dest + '/.venv/bin/python'
    $pre = Invoke-WslExec -WslExe $wsl -Distro $name -Cd $dest -Exec $python -Arguments @($dest + '/dashboard/geo_pilot.py',
        'preflight', '--groups', '1', '--expect-commit', $version.Commit, '--expect-manifest-sha256', $version.ManifestSha256, '--json')
    $report = ConvertFrom-PilotJson $pre.Stdout
    if ($null -eq $report -or ($pre.ExitCode -ne 0 -and $pre.ExitCode -ne 10)) {
        $code = $pre.ExitCode
        if ($code -eq 0) { $code = 1 }
        Write-GeoErr (Get-PilotMessage $code -Action 'pilot')
        if ($null -ne $report) { foreach ($reason in @($report.reasons)) { if ($reason) { Write-GeoInfo ('- ' + $reason) } } }
        Write-GeoErr 'Kurulum kaydi yazilmadi; sorunu giderip bu kisayolu yeniden calistirin.'
        return $code
    }
    Write-GeoOk ('On kontrol gecti: motor ' + $report.engine.label + ', kaynak ' + $report.source.mode + ' ' + $report.source.commit + ' (dogrulandi).')

    $state = [ordered]@{
        schema          = $script:GeoBackendSchema
        distro          = $name
        src             = $dest
        python          = $python
        commit          = $version.Commit
        manifest_sha256 = $version.ManifestSha256
        package_root    = $RepoRoot
        configured_at   = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    }
    Write-BackendState -State $state
    Write-GeoOk ('Kurulum kaydi yazildi: ' + (Get-StatePath))
    Write-Host ''
    Write-GeoOk 'WSL2 arka ucu hazir.'
    Write-GeoInfo 'Masaustu kisayollari: "GEO Workbench" (panoyu acar), "GEO Pilot Baslat" (1 gruplu sinirli pilot),'
    Write-GeoInfo '"GEO Islem Durdur" (pilotu guvenli iptal eder), "GEO Workbench Kapat" (arayuzu kapatir).'
    return 0
}

Write-GeoLog 'INFO' ('setup_wsl_backend start (PowerShell ' + $PSVersionTable.PSVersion + ')')
$exitCode = 1
$lock = $null
try {
    $lock = Enter-GeoLauncherLock -TimeoutSeconds 5
    if ($null -eq $lock) {
        Write-GeoErr 'Baska bir GEO Workbench islemi suruyor; o bitince bu kisayolu yeniden calistirin.'
    } else {
        $exitCode = Invoke-Setup
    }
} catch {
    Write-GeoErr ('Beklenmeyen hata: ' + $_.Exception.Message)
    Write-GeoLog 'ERROR' ($_ | Out-String)
    $exitCode = 1
} finally {
    Exit-GeoLauncherLock $lock
}
$exitCode = [int](@($exitCode)[-1])
Write-GeoLog 'INFO' ('setup_wsl_backend exit ' + $exitCode)
exit $exitCode
