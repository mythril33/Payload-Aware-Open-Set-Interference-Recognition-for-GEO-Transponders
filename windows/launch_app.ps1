# launch_app.ps1 - parameterized launcher for the two SEPARATE Streamlit apps.
#   -App dashboard : Track A, GEO research dashboard (ports 8501-8510)
#   -App rfml      : Track B, RF-ML learning app     (ports 8511-8520)
# Writes "pid;port" to windows\logs\<app>.pid, output to windows\logs\<app>.log
# (stderr to <app>.err.log), waits for /_stcore/health, then opens the browser.
# Console output is ASCII-transliterated Turkish.

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('dashboard', 'rfml')]
    [string]$App
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$LogDir    = Join-Path $ScriptDir 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

if ($App -eq 'dashboard') {
    $DisplayName = 'GEO Arastirma Panosu'
    $VenvName    = '.venv-dashboard'
    $WorkDir     = $RepoRoot
    $AppArg      = 'dashboard\app.py'
    $Ports       = 8501..8510
} else {
    $DisplayName = 'RF-ML Ogrenme Uygulamasi'
    $VenvName    = '.venv-rfml'
    $WorkDir     = Join-Path $RepoRoot 'learning\rfml-basics'
    $AppArg      = 'app.py'
    $Ports       = 8511..8520
}
$VenvPython = Join-Path $RepoRoot ($VenvName + '\Scripts\python.exe')
$PidFile    = Join-Path $LogDir ($App + '.pid')
$OutLog     = Join-Path $LogDir ($App + '.log')
$ErrLog     = Join-Path $LogDir ($App + '.err.log')

# Already running? Then just open the stored URL.
if (Test-Path $PidFile) {
    $content = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($content -match '^(\d+);(\d+)$') {
        $oldPid = [int]$Matches[1]
        $oldPort = [int]$Matches[2]
        $running = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($running) {
            Write-Host ("[OK]    " + $DisplayName + " zaten calisiyor (PID " + $oldPid + ", port " + $oldPort + "). Tarayici aciliyor.")
            Start-Process ("http://127.0.0.1:" + $oldPort)
            exit 0
        }
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
}

if (-not (Test-Path $VenvPython)) {
    Write-Host ("[HATA]  " + $VenvName + " sanal ortami bulunamadi: " + $VenvPython)
    Write-Host "[HATA]  Once kurulumu calistirin: windows\KURULUM.bat (cift tiklayin)."
    exit 1
}

function Test-PortFree {
    param([int]$Port)
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        $listener.Stop()
        return $true
    } catch {
        return $false
    }
}

$Port = 0
foreach ($p in $Ports) {
    if (Test-PortFree -Port $p) { $Port = $p; break }
}
if ($Port -eq 0) {
    Write-Host ("[HATA]  " + $Ports[0] + "-" + $Ports[-1] + " araliginda bos port yok. stop_apps.bat ile eski kopyalari durdurun veya portlari kullanan uygulamalari kapatin.")
    exit 1
}
Write-Host ("[OK]    " + $DisplayName + " baslatiliyor (port " + $Port + "). Ilk acilis yavas olabilir.")

# Start a hidden cmd.exe wrapper that redirects the output itself. Start-Process with
# -RedirectStandardOutput forces UseShellExecute=$false, in which case -WindowStyle is ignored and
# the console child would attach to the launcher's cmd window: the window would linger for the
# app's lifetime and closing it would kill the app (CTRL_CLOSE_EVENT). The wrapper gets its own
# genuinely hidden console, survives the launcher, and exits when streamlit exits, so
# $proc.HasExited still tracks the app; taskkill /T /F in stop_apps.ps1 kills the whole tree.
$CmdLine = ('"{0}" -m streamlit run "{1}" --server.address 127.0.0.1 --server.port {2} ' +
    '--server.headless true 1>"{3}" 2>"{4}"') -f $VenvPython, $AppArg, $Port, $OutLog, $ErrLog
try {
    # One pre-built argument string: Start-Process passes it verbatim, and `cmd /s /c "..."`
    # strips exactly the outer quotes, so the inner quoted paths survive unchanged.
    $proc = Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /s /c "' + $CmdLine + '"') `
        -WorkingDirectory $WorkDir -PassThru -WindowStyle Hidden
} catch {
    Write-Host ("[HATA]  Uygulama baslatilamadi: " + $_.Exception.Message)
    exit 1
}
Set-Content -Path $PidFile -Value ("{0};{1}" -f $proc.Id, $Port) -Encoding ascii
Write-Host ("        PID " + $proc.Id + "; gunluk: " + $OutLog)

# Health poll: http://127.0.0.1:<port>/_stcore/health must answer "ok" within 90 s.
$HealthUrl = "http://127.0.0.1:$Port/_stcore/health"
$deadline = (Get-Date).AddSeconds(90)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { break }
    try {
        $r = Invoke-WebRequest -Uri $HealthUrl -TimeoutSec 5 -UseBasicParsing
        if ("$($r.Content)" -match 'ok') { $healthy = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}

if ($healthy) {
    Write-Host ("[OK]    " + $DisplayName + " hazir: http://127.0.0.1:" + $Port)
    Start-Process ("http://127.0.0.1:" + $Port)
    exit 0
}

Write-Host ("[HATA]  " + $DisplayName + " 90 saniye icinde saglik kontrolune yanit vermedi.")
foreach ($lf in @($OutLog, $ErrLog)) {
    if (Test-Path $lf) {
        Write-Host ("--- Son 20 satir: " + $lf + " ---")
        Get-Content $lf -Tail 20 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ("    " + $_) }
    }
}
Write-Host "[IPUCU] Ilk baslatma antivirus taramasi ve ilk derleme nedeniyle uzun surebilir; birkac dakika bekleyip"
Write-Host ("[IPUCU] tarayicida http://127.0.0.1:" + $Port + " adresini elle deneyin. Sorun surerse windows\logs altindaki")
Write-Host "[IPUCU] gunlukleri inceleyin ve BENIOKU.md dosyasindaki sorun giderme tablosuna bakin."
if ($proc.HasExited) { Remove-Item $PidFile -ErrorAction SilentlyContinue }
exit 1
