# geo_workbench.ps1 - one-click GEO workbench actions for the desktop shortcuts.
#
#   -Action open        open (or reuse) the GEO workbench: WSL2 engine when set up, otherwise the
#                       native Windows dashboard in inspection mode (launch_app.ps1 -App dashboard)
#   -Action pilot       preflight, then start the bounded development pilot (real-exercise, groups
#                       1 or 2, CPU, train/val-select/val-calib only) in WSL2 and open the workbench
#   -Action stop-pilot  cancel the running pilot through geo_pilot.py (ownership-checked)
#   -Action close       stop the workbench UI; a running pilot is never killed by this
#   -Action status      print engine, source and pilot status
#
# The pilot is a bounded development exercise, not the benchmark; nothing here can request
# production, GPU or held-out work. Exit codes are listed in geo_common.ps1. Log:
# windows\logs\geo_workbench.log. ASCII-transliterated Turkish console output.

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('open', 'pilot', 'stop-pilot', 'close', 'status')]
    [string]$Action,
    [ValidateSet('1', '2')]
    [int]$Groups = 1,
    [switch]$NoBrowser,
    [switch]$Force,
    [string]$WslExe = ''
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
. (Join-Path $PSScriptRoot 'geo_common.ps1')

$UiPidFile    = Join-Path (Get-GeoLogDir) 'geo_ui.pid'
$PilotPidFile = Join-Path (Get-GeoLogDir) 'geo_pilot.pid'

# ------------------------------------------------------------------ backend

function Get-Backend {
    $state = Read-BackendState
    if ($null -eq $state) { return [pscustomobject]@{ Status = 'no-state' } }
    $wsl = Find-WslExe -WslExe $WslExe
    if (-not $wsl) { return [pscustomobject]@{ Status = 'no-wsl'; State = $state } }
    $distros = @(Get-WslDistros -WslExe $wsl)
    $match = @($distros | Where-Object { $_.Name -eq "$($state.distro)" })
    if ($match.Count -eq 0) { return [pscustomobject]@{ Status = 'no-distro'; State = $state } }
    if ($match[0].Version -ne 2) { return [pscustomobject]@{ Status = 'wsl1'; State = $state } }
    return [pscustomobject]@{
        Status = 'ok'
        State  = $state
        Wsl    = $wsl
        Distro = "$($state.distro)"
        Src    = "$($state.src)"
        Python = "$($state.python)"
        Script = "$($state.src)" + '/dashboard/geo_pilot.py'
    }
}

function Write-BackendProblem {
    param($Backend)
    switch ($Backend.Status) {
        'no-state'  { Write-GeoWarn (Get-PilotMessage 2) }
        'no-wsl'    { Write-GeoErr 'wsl.exe bulunamadi.'; Write-GeoErr (Get-PilotMessage 3) }
        'no-distro' { Write-GeoErr ('Kayitli WSL dagitimi bulunamadi: ' + $Backend.State.distro); Write-GeoErr (Get-PilotMessage 3) }
        'wsl1'      { Write-GeoErr ('Dagitim ' + $Backend.State.distro + ' WSL1 olarak calisiyor; pilot WSL2 gerektirir (wsl --set-version ' + $Backend.State.distro + ' 2).'); Write-GeoErr (Get-PilotMessage 8) }
    }
}

function Get-BackendProblemCode {
    param($Backend)
    if ($Backend.Status -eq 'no-state') { return 2 }
    if ($Backend.Status -eq 'wsl1') { return 8 }
    return 3
}

function Invoke-GeoPilot {
    param($Backend, [string[]]$Arguments)
    return (Invoke-WslExec -WslExe $Backend.Wsl -Distro $Backend.Distro -Cd $Backend.Src -Exec $Backend.Python `
        -Arguments (@($Backend.Script) + $Arguments))
}

function Get-LatestPilot {
    param($Backend)
    $r = Invoke-GeoPilot -Backend $Backend -Arguments @('status', '--json')
    $j = ConvertFrom-PilotJson $r.Stdout
    if ($null -eq $j -or -not $j.found) { return $null }
    return $j
}

# ------------------------------------------------------------------ UI

function New-UiResult {
    param([int]$ExitCode, [int]$Port)
    return [pscustomobject]@{ ExitCode = $ExitCode; Port = $Port }
}

function Open-WorkbenchBrowser {
    param([int]$Port)
    if ($NoBrowser) { return }
    try {
        Start-Process ('http://127.0.0.1:{0}/' -f $Port)
    } catch {
        Write-GeoWarn ('Tarayici acilamadi; adresi elle acin: http://127.0.0.1:' + $Port + '/')
    }
}

function Open-NativeInspection {
    Write-GeoInfo 'Yerel Windows inceleme modu: pano acilir, ancak gercek RF pilotu yerel Windows uzerinde calismaz.'
    Write-GeoInfo 'Pilot icin WSL2 Ubuntu gerekir: masaustundeki "GEO WSL Kurulumu" kisayolunu bir kez calistirin.'
    $launcher = Join-Path $PSScriptRoot 'launch_app.ps1'
    $null = & $launcher -App dashboard -NoBrowser:$NoBrowser
    return [int]$LASTEXITCODE
}

function Start-WorkbenchUi {
    param($Backend)
    $record = Read-PidRecord -Path $UiPidFile
    if ($null -ne $record -and $record.Engine -eq 'wsl2' -and $record.ProcessId -gt 0) {
        $p = Get-Process -Id $record.ProcessId -ErrorAction SilentlyContinue
        if ($p -and $p.ProcessName -eq 'wsl' -and (Test-UiHealth -Port $record.Port)) {
            Write-GeoOk ('GEO Workbench zaten calisiyor (port ' + $record.Port + ').')
            return (New-UiResult 0 $record.Port)
        }
    }
    $r = Invoke-GeoPilot -Backend $Backend -Arguments @('ui-status', '--json')
    $status = ConvertFrom-PilotJson $r.Stdout
    if ($null -eq $status) {
        Write-GeoErr ('WSL icindeki GEO kopyasindan yanit alinamadi (geo_pilot.py ui-status, cikis kodu ' + $r.ExitCode + ').')
        return (New-UiResult 3 0)
    }
    if ($status.running -and $status.port) {
        $port = [int]$status.port
        if (Wait-UiHealth -Port $port -Seconds 90) {
            Write-PidRecord -Path $UiPidFile -ProcessId 0 -Port $port -Engine 'wsl2'
            Write-GeoOk ('GEO Workbench zaten calisiyor (port ' + $port + ').')
            return (New-UiResult 0 $port)
        }
        Write-GeoErr (Get-PilotMessage 4)
        return (New-UiResult 4 0)
    }
    foreach ($port in $script:GeoUiPorts) {
        if (-not (Test-PortFree -Port $port)) { continue }
        Write-GeoInfo ('GEO Workbench WSL2 icinde baslatiliyor (port ' + $port + '). Ilk acilis bir dakika kadar surebilir.')
        try {
            $proc = Start-WslHidden -WslExe $Backend.Wsl -Distro $Backend.Distro -Cd $Backend.Src -Exec $Backend.Python `
                -Arguments @($Backend.Script, 'serve', '--port', [string]$port)
        } catch {
            Write-GeoErr ('wsl.exe baslatilamadi: ' + $_.Exception.Message)
            return (New-UiResult 1 0)
        }
        Write-PidRecord -Path $UiPidFile -ProcessId $proc.Id -Port $port -Engine 'wsl2'
        if (Wait-UiHealth -Port $port -Seconds 90 -Process $proc) {
            Write-GeoOk ('GEO Workbench hazir: http://127.0.0.1:' + $port + '/ (motor: WSL2, ' + $Backend.Distro + ')')
            return (New-UiResult 0 $port)
        }
        if (-not $proc.HasExited) {
            Write-GeoErr (Get-PilotMessage 4)
            return (New-UiResult 4 0)
        }
        $code = $proc.ExitCode
        if ($null -eq $code) { $code = 1 }
        Remove-Item -LiteralPath $UiPidFile -ErrorAction SilentlyContinue
        Write-GeoLog 'INFO' ('serve exited with ' + $code + ' on port ' + $port)
        if ($code -eq 12) {
            Write-GeoWarn ('Port ' + $port + ' WSL icinde dolu; sonraki port deneniyor.')
            continue
        }
        if ($code -eq 11) {
            $again = ConvertFrom-PilotJson (Invoke-GeoPilot -Backend $Backend -Arguments @('ui-status', '--json')).Stdout
            if ($null -ne $again -and $again.running -and $again.port -and (Wait-UiHealth -Port ([int]$again.port) -Seconds 90)) {
                Write-PidRecord -Path $UiPidFile -ProcessId 0 -Port ([int]$again.port) -Engine 'wsl2'
                Write-GeoOk ('GEO Workbench zaten calisiyor (port ' + $again.port + ').')
                return (New-UiResult 0 ([int]$again.port))
            }
        }
        Write-GeoErr ('Pano sureci beklenmedik sekilde bitti (cikis kodu ' + $code + ').')
        Write-GeoErr (Get-PilotMessage 4)
        return (New-UiResult 4 0)
    }
    Write-GeoErr (Get-PilotMessage 12)
    return (New-UiResult 12 0)
}

# ------------------------------------------------------------------ actions

function Invoke-OpenAction {
    $backend = Get-Backend
    if ($backend.Status -eq 'no-state') {
        Write-GeoInfo 'WSL2 arka ucu kurulu degil; pano yerel Windows inceleme modunda aciliyor.'
        return (Open-NativeInspection)
    }
    if ($backend.Status -ne 'ok') {
        Write-BackendProblem $backend
        $null = Open-NativeInspection
        return (Get-BackendProblemCode $backend)
    }
    $ui = Start-WorkbenchUi -Backend $backend
    if ($ui.ExitCode -ne 0) {
        Write-GeoWarn 'WSL2 panosu acilamadi; yerine yerel Windows inceleme modu aciliyor.'
        $null = Open-NativeInspection
        return $ui.ExitCode
    }
    Open-WorkbenchBrowser -Port $ui.Port
    return 0
}

function Invoke-PilotAction {
    $backend = Get-Backend
    if ($backend.Status -ne 'ok') {
        Write-BackendProblem $backend
        $code = Get-BackendProblemCode $backend
        if ($code -eq 2) { $null = Open-NativeInspection }
        return $code
    }
    $version = Read-PackageVersion
    if ($null -eq $version -or -not $version.Commit -or -not $version.ManifestSha256) {
        Write-GeoErr 'Paket surum bilgisi (VERSION.json: commit ve source_manifest_sha256) okunamadi; kaynak kimligi dogrulanamaz.'
        Write-GeoErr (Get-PilotMessage 20)
        return 20
    }
    Write-GeoInfo ('On kontrol: ' + $Groups + ' grup, commit ' + $version.Commit.Substring(0, 12) + ' ...')
    $pre = Invoke-GeoPilot -Backend $backend -Arguments @('preflight', '--groups', [string]$Groups,
        '--expect-commit', $version.Commit, '--expect-manifest-sha256', $version.ManifestSha256, '--json')
    $report = ConvertFrom-PilotJson $pre.Stdout
    if ($null -eq $report) {
        Write-GeoErr ('On kontrol sonucu okunamadi (geo_pilot.py preflight, cikis kodu ' + $pre.ExitCode + ').')
        Write-GeoErr (Get-PilotMessage $pre.ExitCode -Action 'pilot')
        if ($pre.ExitCode -eq 0) { return 1 }
        return $pre.ExitCode
    }
    if ($pre.ExitCode -eq 10) {
        Write-GeoWarn (Get-PilotMessage 10)
        Write-GeoWarn ('Calisan pilot: JOB_ID=' + $report.running_job)
        $ui = Start-WorkbenchUi -Backend $backend
        if ($ui.ExitCode -eq 0) { Open-WorkbenchBrowser -Port $ui.Port }
        return 10
    }
    if ($pre.ExitCode -ne 0) {
        Write-GeoErr (Get-PilotMessage $pre.ExitCode -Action 'pilot')
        foreach ($reason in @($report.reasons)) { if ($reason) { Write-GeoInfo ('- ' + $reason) } }
        return $pre.ExitCode
    }
    Write-GeoOk ('On kontrol gecti: motor ' + $report.engine.label + ', kaynak ' + $report.source.mode + ' ' + $report.source.commit + ' (dogrulandi).')

    $ui = Start-WorkbenchUi -Backend $backend
    if ($ui.ExitCode -ne 0) {
        Write-GeoErr 'Pano acilamadigi icin pilot baslatilmadi.'
        return $ui.ExitCode
    }

    $before = Get-LatestPilot -Backend $backend
    $beforeId = ''
    if ($null -ne $before) { $beforeId = "$($before.job_id)" }
    try {
        $proc = Start-WslHidden -WslExe $backend.Wsl -Distro $backend.Distro -Cd $backend.Src -Exec $backend.Python `
            -Arguments @($backend.Script, 'run', '--groups', [string]$Groups,
                '--expect-commit', $version.Commit, '--expect-manifest-sha256', $version.ManifestSha256)
    } catch {
        Write-GeoErr ('Pilot denetcisi baslatilamadi: ' + $_.Exception.Message)
        return 1
    }
    [System.IO.File]::WriteAllText($PilotPidFile, ('{0};{1};starting' -f $proc.Id, $Groups), (New-Object System.Text.ASCIIEncoding))
    Write-GeoInfo ('Pilot denetcisi baslatildi (wsl.exe PID ' + $proc.Id + '); is kimligi bekleniyor...')

    $job = $null
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        $latest = Get-LatestPilot -Backend $backend
        if ($null -ne $latest -and "$($latest.job_id)" -ne $beforeId) { $job = $latest; break }
        if ($proc.HasExited) { break }
    }
    if ($null -eq $job) {
        if ($proc.HasExited) {
            $code = $proc.ExitCode
            if ($null -eq $code) { $code = 1 }
            Remove-Item -LiteralPath $PilotPidFile -ErrorAction SilentlyContinue
            if ($code -eq 10) {
                Write-GeoWarn (Get-PilotMessage 10)
                $running = Get-LatestPilot -Backend $backend
                if ($null -ne $running) { Write-GeoWarn ('Calisan pilot: JOB_ID=' + $running.job_id) }
                Open-WorkbenchBrowser -Port $ui.Port
                return 10
            }
            Write-GeoErr ('Pilot denetcisi is baslatmadan bitti (cikis kodu ' + $code + ').')
            Write-GeoErr (Get-PilotMessage $code -Action 'pilot')
            return $code
        }
        Write-GeoWarn (Get-PilotMessage 6)
        Open-WorkbenchBrowser -Port $ui.Port
        return 6
    }
    [System.IO.File]::WriteAllText($PilotPidFile, ('{0};{1};{2}' -f $proc.Id, $Groups, $job.job_id), (New-Object System.Text.ASCIIEncoding))
    Write-GeoOk (Get-PilotMessage 0 -Action 'pilot')
    Write-GeoInfo ('JOB_ID=' + $job.job_id + '  durum: ' + $job.state + '  grup: ' + $Groups)
    Write-GeoInfo ('Cikti klasoru (WSL icinde): ' + $job.job_dir)
    Write-GeoInfo 'Asamalar ve gunluk panoda izlenir; durdurmak icin "GEO Islem Durdur" kisayolunu kullanin.'
    Write-GeoInfo 'Pilot, 21.350 gozlemlik benchmark degildir; uretim/GPU/held-out kapilari kapali kalir.'
    Open-WorkbenchBrowser -Port $ui.Port
    return 0
}

function Invoke-StopPilotAction {
    $backend = Get-Backend
    if ($backend.Status -eq 'no-state') {
        Write-GeoInfo 'WSL2 arka ucu kurulu degil; calisan bir GEO pilotu olamaz.'
        return 3
    }
    if ($backend.Status -ne 'ok') {
        Write-BackendProblem $backend
        return (Get-BackendProblemCode $backend)
    }
    $r = Invoke-GeoPilot -Backend $backend -Arguments @('cancel')
    Write-GeoLog 'INFO' ('cancel output: ' + $r.Stdout)
    if ($r.ExitCode -eq 0) {
        $jobId = ''
        if ($r.Stdout -match 'JOB_ID=(\S+)') { $jobId = $Matches[1] }
        Write-GeoOk ('Pilot guvenli bicimde iptal edildi. JOB_ID=' + $jobId)
        Write-GeoInfo 'Kismi ciktilar ve gunluk korundu; sonuc basarili sayilmaz.'
        Remove-Item -LiteralPath $PilotPidFile -ErrorAction SilentlyContinue
    } elseif ($r.ExitCode -eq 3) {
        Write-GeoOk (Get-PilotMessage 3 -Action 'stop-pilot')
        Remove-Item -LiteralPath $PilotPidFile -ErrorAction SilentlyContinue
    } else {
        Write-GeoErr (Get-PilotMessage $r.ExitCode -Action 'stop-pilot')
    }
    return $r.ExitCode
}

function Get-NativeRunHome {
    if ($env:GEO_DASHBOARD_HOME) { return $env:GEO_DASHBOARD_HOME }
    return (Join-Path (Join-Path (Join-Path $env:USERPROFILE '.local') 'share') 'geo-dashboard')
}

function Get-NativeRunningJobs {
    $jobsDir = Join-Path (Get-NativeRunHome) 'jobs'
    if (-not (Test-Path -LiteralPath $jobsDir -PathType Container)) { return @() }
    $found = @(foreach ($dir in @(Get-ChildItem -LiteralPath $jobsDir -Directory -ErrorAction SilentlyContinue)) {
        $jobFile = Join-Path $dir.FullName 'job.json'
        try {
            $job = Get-Content -LiteralPath $jobFile -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        } catch {
            continue
        }
        if ("$($job.state)" -eq 'running') { $dir.Name }
    })
    return $found
}

function Get-NativeDashboardProcess {
    $pidFile = Join-Path (Get-GeoLogDir) 'dashboard.pid'
    if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) { return $null }
    $content = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ("$content" -notmatch '^(\d+);(\d+)$') { return $null }
    return (Get-Process -Id ([int]$Matches[1]) -ErrorAction SilentlyContinue)
}

function Stop-NativeDashboard {
    $pidFile = Join-Path (Get-GeoLogDir) 'dashboard.pid'
    if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) { return 0 }
    $content = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ("$content" -notmatch '^(\d+);(\d+)$') {
        Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
        Write-GeoWarn 'dashboard.pid bozuktu; temizlendi.'
        return 0
    }
    $procId = [int]$Matches[1]
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if (-not $proc) {
        Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
        Write-GeoInfo 'Yerel pano zaten calismiyordu; eski kayit temizlendi.'
        return 0
    }
    $written = (Get-Item -LiteralPath $pidFile).LastWriteTime
    $started = $null
    try { $started = $proc.StartTime } catch { }
    # launch_app.ps1 records its hidden cmd.exe wrapper right after starting it; a later start time
    # means the PID was recycled by an unrelated process.
    if ($proc.ProcessName -ne 'cmd' -or $null -eq $started -or $started -gt $written.AddSeconds(5)) {
        Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
        Write-GeoWarn ('dashboard.pid icindeki PID ' + $procId + ' artik yerel panoya ait gorunmuyor; sonlandirilmadi.')
        return 41
    }
    & taskkill.exe /PID $procId /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-GeoErr ('Yerel pano durdurulamadi (taskkill cikis kodu ' + $LASTEXITCODE + ').')
        return 1
    }
    Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
    Write-GeoOk 'Yerel GEO panosu (inceleme modu) durduruldu.'
    return 0
}

function Invoke-CloseAction {
    $backend = Get-Backend
    $runningPilot = $null
    if ($backend.Status -eq 'ok') {
        $latest = Get-LatestPilot -Backend $backend
        if ($null -ne $latest -and "$($latest.state)" -eq 'running') { $runningPilot = "$($latest.job_id)" }
    }
    $nativeJobs = @()
    if ($null -ne (Get-NativeDashboardProcess)) { $nativeJobs = @(Get-NativeRunningJobs) }
    if ($runningPilot -or $nativeJobs.Count -gt 0) {
        if ($runningPilot) {
            Write-GeoWarn ('Bir GEO pilotu calisiyor: JOB_ID=' + $runningPilot)
            Write-GeoWarn 'Arayuz kapatilsa bile pilot WSL icinde calismaya devam eder ve sonucu kaydedilir.'
            Write-GeoWarn 'Pilotu durdurmak icin "GEO Islem Durdur" kisayolunu kullanin; bu islem pilotu durdurmaz.'
        }
        if ($nativeJobs.Count -gt 0) {
            Write-GeoWarn ('Yerel panoda calisan is(ler) var: ' + ($nativeJobs -join ', ') + '. Yerel pano kapatilirsa bu is(ler) sonlandirilir.')
        }
        if (-not $Force) {
            if (-not (Read-Consent 'Arayuz yine de kapatilsin mi?')) {
                Write-GeoInfo (Get-PilotMessage 5)
                return 5
            }
        }
    }
    $code = 0
    if ($backend.Status -eq 'ok') {
        $r = Invoke-GeoPilot -Backend $backend -Arguments @('ui-stop')
        Write-GeoLog 'INFO' ('ui-stop output: ' + $r.Stdout)
        if ($r.ExitCode -eq 0) {
            Remove-Item -LiteralPath $UiPidFile -ErrorAction SilentlyContinue
            Write-GeoOk 'GEO Workbench arayuzu (WSL2) durduruldu. Kayitlar ve ciktilar silinmedi.'
        } elseif ($r.ExitCode -eq 3) {
            Remove-Item -LiteralPath $UiPidFile -ErrorAction SilentlyContinue
            Write-GeoInfo 'WSL2 icinde calisan bir GEO Workbench arayuzu yok.'
        } else {
            Write-GeoErr (Get-PilotMessage $r.ExitCode -Action 'close')
            $code = $r.ExitCode
        }
    } elseif ($backend.Status -ne 'no-state') {
        Write-BackendProblem $backend
    }
    $native = Stop-NativeDashboard
    if ($code -eq 0 -and $native -ne 0) { $code = $native }
    return $code
}

function Invoke-StatusAction {
    Write-Host '--- GEO Workbench durumu ---'
    $version = Read-PackageVersion
    if ($null -eq $version) {
        Write-GeoInfo 'Paket: VERSION.json yok (CI paketi degil; kaynak kimligi bu klasorden dogrulanamaz).'
    } else {
        Write-GeoInfo ('Paket: surum ' + $version.Version + ', commit ' + $version.Commit)
    }
    $backend = Get-Backend
    if ($backend.Status -ne 'ok') {
        Write-GeoInfo 'Motor: yerel Windows (yalniz inceleme)'
        Write-BackendProblem $backend
        if ($null -ne (Get-NativeDashboardProcess)) { Write-GeoInfo 'Yerel pano: calisiyor' } else { Write-GeoInfo 'Yerel pano: calismiyor' }
    } else {
        $preArgs = @('preflight', '--groups', '1', '--json')
        if ($null -ne $version -and $version.Commit -and $version.ManifestSha256) {
            $preArgs = @('preflight', '--groups', '1', '--expect-commit', $version.Commit,
                '--expect-manifest-sha256', $version.ManifestSha256, '--json')
        }
        $pre = ConvertFrom-PilotJson (Invoke-GeoPilot -Backend $backend -Arguments $preArgs).Stdout
        if ($null -eq $pre) {
            Write-GeoErr (Get-PilotMessage 3)
        } else {
            $verified = 'dogrulanmadi'
            if ($pre.source.verified) { $verified = 'dogrulandi' }
            Write-GeoInfo ('Motor: ' + $pre.engine.label + ' (' + $backend.Distro + ')')
            Write-GeoInfo ('Kaynak: ' + $pre.source.mode + ' ' + $pre.source.commit + ' (' + $verified + ')')
            if (@($pre.codes).Count -gt 0) { Write-GeoInfo ('On kontrol kodlari: ' + (@($pre.codes) -join ', ')) }
        }
        $ui = ConvertFrom-PilotJson (Invoke-GeoPilot -Backend $backend -Arguments @('ui-status', '--json')).Stdout
        if ($null -ne $ui) { Write-GeoInfo ('Arayuz: ' + $ui.state + ' (port ' + $ui.port + ')') }
        $latest = Get-LatestPilot -Backend $backend
        if ($null -eq $latest) {
            Write-GeoInfo 'Pilot: henuz calistirilmamis'
        } else {
            Write-GeoInfo ('Pilot: JOB_ID=' + $latest.job_id + ' durum=' + $latest.state + ' asama=' + $latest.stage +
                ' gecen sure=' + $latest.elapsed_s + ' s (zaman olcer, tamamlanma yuzdesi degildir) dogrulandi=' + $latest.verified)
            Write-GeoInfo ('Cikti klasoru (WSL icinde): ' + $latest.job_dir)
        }
    }
    Write-GeoInfo 'Benchmark: TAMAMLANMADI. Arastirma kapilari KAPALI; uretim/GPU/held-out yetkisi yok.'
    return 0
}

# ------------------------------------------------------------------ main

Write-GeoLog 'INFO' ('geo_workbench -Action ' + $Action + ' -Groups ' + $Groups + ' (PowerShell ' + $PSVersionTable.PSVersion + ')')
$exitCode = 1
$lock = $null
try {
    $locked = $true
    if ($Action -in @('open', 'pilot', 'close')) {
        $lock = Enter-GeoLauncherLock
        if ($null -eq $lock) {
            Write-GeoErr 'Baska bir GEO Workbench islemi uzun suredir suruyor; biraz sonra yeniden deneyin.'
            $locked = $false
        }
    }
    if ($locked) {
        switch ($Action) {
            'open'       { $exitCode = Invoke-OpenAction }
            'pilot'      { $exitCode = Invoke-PilotAction }
            'stop-pilot' { $exitCode = Invoke-StopPilotAction }
            'close'      { $exitCode = Invoke-CloseAction }
            'status'     { $exitCode = Invoke-StatusAction }
        }
    }
} catch {
    Write-GeoErr ('Beklenmeyen hata: ' + $_.Exception.Message)
    Write-GeoLog 'ERROR' ($_ | Out-String)
    $exitCode = 1
} finally {
    Exit-GeoLauncherLock $lock
}
$exitCode = [int](@($exitCode)[-1])
Write-GeoLog 'INFO' ('geo_workbench -Action ' + $Action + ' exit ' + $exitCode)
exit $exitCode
