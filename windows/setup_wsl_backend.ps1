# setup_wsl_backend.ps1 - consent-gated, one-time WSL2 setup for the one-click GEO pilot.
#
# Steps (each one explained and logged; nothing is installed without an explicit [E/H] answer):
#   1. read VERSION.json of this CI package and check geo-source.bundle against it (a Git checkout
#      of the scripts cannot be used: the package's full-history Git bundle is the source)
#   2. find wsl.exe and an Ubuntu distribution; without one, offer `wsl --install -d Ubuntu-24.04`
#      (enabling WSL itself needs administrator approval through UAC and possibly a reboot)
#   3. check WSL2, python3 >= 3.10 and a non-root default Linux user inside the distribution
#   4. clone the bundle into the WSL ext4 home (~/geo-workbench-src) with
#      windows/wsl/geo_wsl_setup.py install-git (git missing: install it with consent, retry once);
#      an existing different copy is moved aside, never deleted, after a running UI is stopped
#   5. create ~/geo-workbench-src/.venv and install the CPU dependencies (geo_wsl_setup.py venv)
#   6. run geo_pilot.py preflight against this package's commit
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
$UiPidFile = Join-Path (Get-GeoLogDir) 'geo_ui.pid'

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
    Write-GeoInfo 'Onemli: Ubuntu penceresinde kullanici adi ve parolayi olusturduktan sonra o pencere bir Ubuntu'
    Write-GeoInfo 'komut satirinda bekler. Pencereyi kapatin veya "exit" yazip Enter tuslayin; bu kurulum ancak o zaman devam eder.'
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
    $code = $null
    if ($null -ne $proc) { try { $code = $proc.ExitCode } catch { $code = $null } }
    Write-GeoLog 'INFO' ('wsl --install exit ' + $code)
    # 3010 = ERROR_SUCCESS_REBOOT_REQUIRED; anything else (or no code at all) is a failed install.
    if ($null -ne $code -and ($code -eq 0 -or $code -eq 3010)) {
        if ($code -eq 3010) { Write-GeoInfo 'Windows, kurulumun tamamlanmasi icin yeniden baslatma istiyor.' }
        Write-GeoOk (Get-PilotMessage 7)
        return 7
    }
    Write-GeoErr ('wsl --install basarisiz oldu (cikis kodu ' + $code + '). Ubuntu kurulmadi.')
    Write-GeoErr 'Windows Update ile sistemi guncelleyin, internet baglantisini kontrol edin ve bu kisayolu yeniden calistirin.'
    return 1
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

function Get-LinuxUser {
    param([string]$WslPath, [string]$Name)
    $uidRun = Invoke-WslExec -WslExe $WslPath -Distro $Name -Cd '~' -Exec 'id' -Arguments @('-u')
    $nameRun = Invoke-WslExec -WslExe $WslPath -Distro $Name -Cd '~' -Exec 'id' -Arguments @('-un')
    $uidText = "$($uidRun.Stdout)".Trim()
    $userText = "$($nameRun.Stdout)".Trim()
    if ($uidRun.ExitCode -ne 0 -or $uidText -notmatch '^\d{1,10}$' -or $nameRun.ExitCode -ne 0 -or -not $userText) { return $null }
    return [pscustomobject]@{ Uid = [long]$uidText; User = $userText }
}

function Install-AptPackageWithConsent {
    param([string]$WslPath, [string]$Name, [string]$Package, [int]$Code)
    Write-GeoWarn (Get-PilotMessage $Code)
    Write-GeoInfo ('Yeni bir pencerede "sudo apt-get install -y ' + $Package + '" calistirilir; Ubuntu kendi parolanizi sorabilir.')
    if (-not (Read-Consent ($Package + ' simdi kurulsun mu?'))) { return $false }
    foreach ($step in @(@('sudo', 'apt-get', 'install', '-y', $Package),
                        @('sudo', 'apt-get', 'update'),
                        @('sudo', 'apt-get', 'install', '-y', $Package))) {
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
        if ($proc.ExitCode -eq 0 -and $step[-1] -eq $Package) { return $true }
    }
    return $false
}

function Invoke-SetupPy {
    param([string]$WslPath, [string]$Name, [string[]]$Arguments)
    return (Invoke-WslExec -WslExe $WslPath -Distro $Name -Cd '~' -Exec 'python3' -Arguments $Arguments)
}

function Stop-OldUiWithConsent {
    # serve keeps the old tree's code in memory and would be reused by "GEO Workbench" after the swap.
    param([string]$WslPath, [string]$Name, [string]$Dest, [string]$OldPython)
    $pilotScript = $Dest + '/dashboard/geo_pilot.py'
    $ui = ConvertFrom-PilotJson (Invoke-WslExec -WslExe $WslPath -Distro $Name -Cd $Dest -Exec $OldPython -Arguments @($pilotScript, 'ui-status', '--json')).Stdout
    if ($null -eq $ui -or -not $ui.running) { return 0 }
    Write-GeoWarn ('Eski kopyadan calisan bir GEO Workbench arayuzu var (port ' + $ui.port + '). Kopya degistirilmeden once kapatilmalidir.')
    if (-not (Read-Consent 'Calisan arayuz kapatilsin mi?')) {
        Write-GeoErr 'Arayuz calisirken kopya degistirilmez. "GEO Workbench Kapat" ile kapatip bu kisayolu yeniden calistirin.'
        return 5
    }
    $stop = Invoke-WslExec -WslExe $WslPath -Distro $Name -Cd $Dest -Exec $OldPython -Arguments @($pilotScript, 'ui-stop')
    if ($stop.ExitCode -eq 0 -or $stop.ExitCode -eq 3) {
        Remove-Item -LiteralPath $UiPidFile -ErrorAction SilentlyContinue
        Write-GeoOk 'Eski arayuz kapatildi.'
        return 0
    }
    Write-GeoErr (Get-PilotMessage $stop.ExitCode -Action 'close')
    Write-GeoErr 'Arayuz kapatilamadigi icin kopya degistirilmedi.'
    return $stop.ExitCode
}

function Invoke-Setup {
    Write-Host '====================================================='
    Write-Host ' GEO WSL Kurulumu - gercek RF pilotu icin WSL2 arka ucu'
    Write-Host '====================================================='
    Write-GeoInfo 'Bu kurulum bir kez yapilir ve sunlari yapar:'
    Write-GeoInfo ' - bu paketin Git paketinden (geo-source.bundle) WSL2 Ubuntu ev dizinine (~/geo-workbench-src)'
    Write-GeoInfo '   ayni commit icin gercek bir Git kopyasi olusturur,'
    Write-GeoInfo ' - orada bir Python sanal ortami kurar (PyTorch CPU dahil, birkac GB indirme),'
    Write-GeoInfo ' - pilot on kontrolunu calistirir ve sonucu %LOCALAPPDATA%\GEO-Workbench altina kaydeder.'
    Write-GeoInfo 'Gerekirse WSL/Ubuntu kurulumu ile git ve python3-venv paketleri icin ayrica onay istenir.'
    Write-GeoInfo 'Hicbir uretim, GPU veya held-out kapisi acilmaz; pilot 21.350 gozlemlik benchmark degildir.'
    Write-Host ''
    if (-not (Read-Consent 'Devam edilsin mi?')) {
        Write-GeoInfo (Get-PilotMessage 5)
        return 5
    }

    Write-Host '--- 1/7 Paket ---'
    $version = Read-PackageVersion -Root $RepoRoot
    $setupPy = Join-Path (Join-Path (Join-Path $RepoRoot 'windows') 'wsl') 'geo_wsl_setup.py'
    if ($null -eq $version -or -not $version.Commit -or -not $version.SourceBundle -or -not $version.SourceBundleSha256 -or
        -not (Test-Path -LiteralPath $setupPy -PathType Leaf)) {
        Write-GeoErr (Get-PilotMessage 9)
        return 9
    }
    $bundleFile = Join-Path $RepoRoot $version.SourceBundle
    if (-not (Test-Path -LiteralPath $bundleFile -PathType Leaf)) {
        Write-GeoErr ('Git paketi bulunamadi: ' + $bundleFile)
        Write-GeoErr (Get-PilotMessage 9)
        return 9
    }
    if ($version.SourceBundleHead -cne $version.Commit) {
        Write-GeoErr ('VERSION.json: source_bundle_head (' + $version.SourceBundleHead + ') commit ile ayni degil (' + $version.Commit + ').')
        Write-GeoErr (Get-PilotMessage 9)
        return 9
    }
    $bundleSha = (Get-FileHash -LiteralPath $bundleFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($bundleSha -cne $version.SourceBundleSha256) {
        Write-GeoErr ('geo-source.bundle ozeti VERSION.json ile eslesmiyor (' + $bundleSha + ').')
        Write-GeoErr (Get-PilotMessage 9)
        return 9
    }
    Write-GeoOk ('Paket surumu ' + $version.Version + ', commit ' + $version.Commit + ' (Git paketi dogrulandi).')

    Write-Host '--- 2/7 WSL ---'
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

    Write-Host '--- 3/7 Python ve Linux kullanicisi ---'
    $py = Get-PythonVersionOk -WslPath $wsl -Name $name
    if ($null -eq $py -or -not $py.Ok) {
        Write-GeoErr (Get-PilotMessage 8)
        Write-GeoErr ('Ubuntu icinde python3 kurun (sudo apt-get install -y python3) ve bu kisayolu yeniden calistirin.')
        return 8
    }
    Write-GeoOk ('python3 ' + $py.Text)
    $linux = Get-LinuxUser -WslPath $wsl -Name $name
    if ($null -eq $linux) {
        Write-GeoErr 'WSL icindeki Linux kullanicisi belirlenemedi (id -u / id -un).'
        return 1
    }
    if ($linux.Uid -eq 0) {
        Write-GeoErr ('Dagitim ' + $name + ' root (uid 0) olarak aciliyor: Ubuntu ilk acilistaki Linux kullanicisi olusturulmamis.')
        Write-GeoErr 'Baslat menusunden Ubuntu uygulamasini bir kez acin, Linux kullanici adi ve parolanizi olusturun,'
        Write-GeoErr 'pencereyi kapatin (veya "exit" yazin) ve sonra bu kisayolu yeniden calistirin.'
        Write-GeoErr (Get-PilotMessage 8)
        return 8
    }
    Write-GeoOk ('Linux kullanicisi: ' + $linux.User + ' (uid ' + $linux.Uid + ')')
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
    $bundleWsl = $pkgPath.TrimEnd('/') + '/' + $version.SourceBundle

    Write-Host '--- 4/7 Kaynak (Git kopyasi) ---'
    Write-GeoInfo ('Git paketi (Windows): ' + $bundleFile)
    Write-GeoInfo ('Hedef (WSL ext4): ' + $dest)
    $gitArgs = @($pkgSetup, 'install-git', '--bundle', $bundleWsl, '--commit', $version.Commit, '--to', $dest)
    $install = Invoke-SetupPy -WslPath $wsl -Name $name -Arguments ($gitArgs + @('--json'))
    if ($install.ExitCode -eq 17) {
        if (-not (Install-AptPackageWithConsent -WslPath $wsl -Name $name -Package 'git' -Code 17)) {
            Write-GeoErr (Get-PilotMessage 17)
            return 17
        }
        $install = Invoke-SetupPy -WslPath $wsl -Name $name -Arguments ($gitArgs + @('--json'))
    }
    $result = ConvertFrom-PilotJson $install.Stdout
    $reused = $false
    if ($install.ExitCode -eq 13) {
        $existing = ''
        if ($null -ne $result) { $existing = "$($result.existing_commit)" }
        $isGit = ((Invoke-WslExec -WslExe $wsl -Distro $name -Cd '~' -Exec 'test' -Arguments @('-d', $dest + '/.git')).ExitCode -eq 0)
        if ($isGit -and $existing -ceq $version.Commit) {
            Write-GeoOk 'WSL icinde ayni commit icin bir Git kopyasi zaten var; yeniden kullaniliyor (temizligi sonraki adimlarda denetlenir).'
            $reused = $true
        } else {
            $kind = 'Git kopyasi degil'
            if ($isGit) { $kind = 'Git kopyasi' }
            Write-GeoWarn ('WSL icinde baska bir kopya var (commit ' + $existing + ', ' + $kind + ').')
            Write-GeoWarn 'Mevcut kopya silinmez; ".previous-<zaman>" ekiyle kenara tasinir. Calisan bir pilot varsa once onu bitirin.'
            $oldPython = $dest + '/.venv/bin/python'
            $old = Invoke-WslExec -WslExe $wsl -Distro $name -Cd '~' -Exec 'test' -Arguments @('-x', $oldPython)
            if ($old.ExitCode -eq 0) {
                $oldStatus = ConvertFrom-PilotJson (Invoke-WslExec -WslExe $wsl -Distro $name -Cd $dest -Exec $oldPython -Arguments @($dest + '/dashboard/geo_pilot.py', 'status', '--json')).Stdout
                if ($null -ne $oldStatus -and $oldStatus.found -and "$($oldStatus.state)" -eq 'running') {
                    Write-GeoErr ('Mevcut kopyada bir pilot calisiyor (JOB_ID=' + $oldStatus.job_id + '); kopya degistirilmedi.')
                    return 10
                }
                $uiCode = Stop-OldUiWithConsent -WslPath $wsl -Name $name -Dest $dest -OldPython $oldPython
                if ($uiCode -ne 0) { return $uiCode }
            }
            if (-not (Read-Consent 'Yeni surum kurulsun ve eski kopya kenara tasinsin mi?')) {
                Write-GeoInfo (Get-PilotMessage 5)
                return 5
            }
            $install = Invoke-SetupPy -WslPath $wsl -Name $name -Arguments ($gitArgs + @('--replace', '--json'))
            $result = ConvertFrom-PilotJson $install.Stdout
            if ($install.ExitCode -eq 0) { Remove-Item -LiteralPath $UiPidFile -ErrorAction SilentlyContinue }
        }
    }
    if ($install.ExitCode -ne 0 -and -not $reused) {
        Write-GeoErr (Get-PilotMessage $install.ExitCode)
        if ($null -ne $result) {
            if ($result.message) { Write-GeoInfo ('geo_wsl_setup: ' + $result.message) }
            foreach ($problem in @($result.problems)) { if ($problem) { Write-GeoInfo ('- ' + $problem) } }
        }
        return $install.ExitCode
    }
    if (-not $reused) {
        Write-GeoOk ('Git kopyasi olusturuldu ve dogrulandi: ' + $dest + ' (commit ' + $version.Commit + ')')
        if ($null -ne $result -and $result.previous) { Write-GeoInfo ('Eski kopya: ' + $result.previous) }
    }

    Write-Host '--- 5/7 Sanal ortam (uzun surebilir) ---'
    $destSetup = $dest + '/windows/wsl/geo_wsl_setup.py'
    $venvArgs = @($destSetup, 'venv', '--src', $dest, '--json')
    $venv = Invoke-SetupPy -WslPath $wsl -Name $name -Arguments $venvArgs
    if ($venv.ExitCode -eq 15) {
        if (-not (Install-AptPackageWithConsent -WslPath $wsl -Name $name -Package 'python3-venv' -Code 15)) {
            Write-GeoErr (Get-PilotMessage 15)
            return 15
        }
        $venv = Invoke-SetupPy -WslPath $wsl -Name $name -Arguments $venvArgs
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

    Write-Host '--- 6/7 Pilot on kontrolu ---'
    $python = $dest + '/.venv/bin/python'
    $preArgs = @($dest + '/dashboard/geo_pilot.py', 'preflight', '--groups', '1') + (Get-ExpectArgs -Commit $version.Commit) + @('--json')
    $pre = Invoke-WslExec -WslExe $wsl -Distro $name -Cd $dest -Exec $python -Arguments $preArgs
    $report = ConvertFrom-PilotJson $pre.Stdout
    # A running job (10, 18) does not make the copy unusable; the pilot shortcut reports it later.
    if ($null -eq $report -or ($pre.ExitCode -ne 0 -and $pre.ExitCode -ne 10 -and $pre.ExitCode -ne 18)) {
        $code = $pre.ExitCode
        if ($code -eq 0) { $code = 1 }
        Write-GeoErr (Get-PilotMessage $code -Action 'pilot')
        if ($null -ne $report) { foreach ($reason in @($report.reasons)) { if ($reason) { Write-GeoInfo ('- ' + $reason) } } }
        Write-GeoErr 'Kurulum kaydi yazilmadi; sorunu giderip bu kisayolu yeniden calistirin.'
        return $code
    }
    Write-GeoOk ('On kontrol gecti: motor ' + $report.engine.label + ', kaynak ' + $report.source.mode + ' ' + $report.source.commit + ' (dogrulandi).')

    Write-Host '--- 7/7 Kurulum kaydi ---'
    $state = [ordered]@{
        schema          = $script:GeoBackendSchema
        distro          = $name
        src             = $dest
        python          = $python
        commit          = $version.Commit
        source_mode     = 'git'
        manifest_sha256 = $version.ManifestSha256
        linux_user      = $linux.User
        uid             = $linux.Uid
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
