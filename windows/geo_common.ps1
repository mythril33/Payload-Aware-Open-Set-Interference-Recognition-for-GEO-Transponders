# geo_common.ps1 - shared helpers for the one-click GEO workbench scripts (dot-sourced).
#
# Windows PowerShell 5.1 and PowerShell 7 compatible; ASCII only. Console messages are
# ASCII-transliterated Turkish. Everything WSL-side goes through `wsl.exe -d <distro> [--cd <dir>]
# --exec <program> <args...>` (no shell string is ever built). The governed pilot itself is
# dashboard/geo_pilot.py inside the WSL copy; these helpers only call it and map its exit codes.
#
# Windows-side exit codes (geo_workbench.ps1, setup_wsl_backend.ps1); 10-41 come from geo_pilot.py
# and 13-16/20 from windows/wsl/geo_wsl_setup.py:
#   0 OK, 1 unexpected error, 2 WSL backend not set up, 3 WSL/distribution missing (or: no running
#   pilot), 4 dashboard did not become healthy, 5 declined by the user, 6 pilot job id not seen in
#   60 s, 7 WSL/Ubuntu installation started (finish it, then rerun setup), 8 distribution unsuitable
#   (WSL1 or python3 < 3.10), 9 package files missing.

$script:GeoWindowsDir = $PSScriptRoot
$script:GeoLogPathOverride = $null
$script:GeoBackendSchema = 'GEO-workbench-wsl-backend/1'
$script:GeoUiPorts = 8531..8540
$script:GeoLockName = 'Local\GEO-Workbench-Launcher'

# ------------------------------------------------------------------ locations and logging

function Get-GeoWindowsDir {
    return $script:GeoWindowsDir
}

function Get-RepoRoot {
    return (Split-Path -Parent $script:GeoWindowsDir)
}

function Get-GeoLogDir {
    return (Join-Path $script:GeoWindowsDir 'logs')
}

function Get-GeoLogPath {
    if ($script:GeoLogPathOverride) { return $script:GeoLogPathOverride }
    return (Join-Path (Get-GeoLogDir) 'geo_workbench.log')
}

function Write-GeoLog {
    param([string]$Level, [string]$Message)
    try {
        $path = Get-GeoLogPath
        [void][System.IO.Directory]::CreateDirectory((Split-Path -Parent $path))
        if ([System.IO.File]::Exists($path) -and ((New-Object System.IO.FileInfo($path)).Length -gt 5MB)) {
            [System.IO.File]::Copy($path, $path + '.1', $true)
            [System.IO.File]::Delete($path)
        }
        $line = '{0} [{1}] [{2}] {3}{4}' -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'), $PID, $Level, $Message, [Environment]::NewLine
        [System.IO.File]::AppendAllText($path, $line, (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
}

function Write-GeoOk   ([string]$m) { Write-Host ('[OK]    ' + $m) -ForegroundColor Green;  Write-GeoLog 'OK' $m }
function Write-GeoWarn ([string]$m) { Write-Host ('[UYARI] ' + $m) -ForegroundColor Yellow; Write-GeoLog 'WARN' $m }
function Write-GeoErr  ([string]$m) { Write-Host ('[HATA]  ' + $m) -ForegroundColor Red;    Write-GeoLog 'ERROR' $m }
function Write-GeoInfo ([string]$m) { Write-Host ('        ' + $m);                         Write-GeoLog 'INFO' $m }

# ------------------------------------------------------------------ consent and lock

function Read-Consent {
    param([string]$Prompt)
    try {
        $answer = Read-Host ($Prompt + ' [E/H]')
    } catch {
        return $false
    }
    return ("$answer".Trim() -match '^[Ee]')
}

function Enter-GeoLauncherLock {
    param([int]$TimeoutSeconds = 180)
    $mutex = New-Object System.Threading.Mutex($false, $script:GeoLockName)
    try {
        if ($mutex.WaitOne(0)) { return $mutex }
        Write-GeoInfo 'Baska bir GEO Workbench islemi suruyor; bitmesi bekleniyor...'
        if ($mutex.WaitOne($TimeoutSeconds * 1000)) { return $mutex }
    } catch {
        # A launcher that died while holding the lock leaves it abandoned; the wait then owns it.
        $e = $_.Exception
        if ($e -is [System.Threading.AbandonedMutexException] -or $e.InnerException -is [System.Threading.AbandonedMutexException]) {
            return $mutex
        }
    }
    $mutex.Dispose()
    return $null
}

function Exit-GeoLauncherLock {
    param($Mutex)
    if ($null -eq $Mutex) { return }
    try { $Mutex.ReleaseMutex() } catch { }
    $Mutex.Dispose()
}

# ------------------------------------------------------------------ package version and backend state

function Read-PackageVersion {
    param([string]$Root = '')
    if (-not $Root) { $Root = Get-RepoRoot }
    $path = Join-Path $Root 'VERSION.json'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    try {
        $data = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }
    if ($null -eq $data) { return $null }
    $commit = $null
    $manifest = $null
    if ("$($data.commit)" -match '^[0-9a-f]{40}$') { $commit = "$($data.commit)" }
    if ("$($data.source_manifest_sha256)" -match '^[0-9a-f]{64}$') { $manifest = "$($data.source_manifest_sha256)" }
    return [pscustomobject]@{
        Version        = "$($data.version)"
        Commit         = $commit
        ManifestSha256 = $manifest
        Path           = $path
    }
}

function Get-StatePath {
    $base = $env:LOCALAPPDATA
    if (-not $base) { $base = Join-Path $env:USERPROFILE 'AppData\Local' }
    return (Join-Path (Join-Path $base 'GEO-Workbench') 'wsl_backend.json')
}

function Test-BackendState {
    param($State)
    if ($null -eq $State) { return $false }
    if ("$($State.schema)" -ne $script:GeoBackendSchema) { return $false }
    if ("$($State.distro)" -notmatch '^[A-Za-z0-9._-]+$') { return $false }
    $src = "$($State.src)"
    if ($src -notmatch '^/[^"]+$' -or $src -match '^/mnt(/|$)') { return $false }
    if ("$($State.python)" -ne ($src + '/.venv/bin/python')) { return $false }
    if ("$($State.commit)" -notmatch '^[0-9a-f]{40}$') { return $false }
    return $true
}

function Read-BackendState {
    param([string]$Path = '')
    if (-not $Path) { $Path = Get-StatePath }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        $state = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }
    if (-not (Test-BackendState $state)) { return $null }
    return $state
}

function Write-BackendState {
    param([Parameter(Mandatory = $true)]$State, [string]$Path = '')
    if (-not $Path) { $Path = Get-StatePath }
    [void][System.IO.Directory]::CreateDirectory((Split-Path -Parent $Path))
    $json = $State | ConvertTo-Json -Depth 5
    $tmp = $Path + '.tmp'
    [System.IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding($false)))
    if ([System.IO.File]::Exists($Path)) { [System.IO.File]::Delete($Path) }
    [System.IO.File]::Move($tmp, $Path)
}

# ------------------------------------------------------------------ pid records (windows\logs\*.pid)

function Read-PidRecord {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $line = Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue | Select-Object -First 1
    if ("$line" -notmatch '^(\d+);(\d+);([A-Za-z0-9-]+)$') { return $null }
    return [pscustomobject]@{ ProcessId = [int]$Matches[1]; Port = [int]$Matches[2]; Engine = $Matches[3] }
}

function Write-PidRecord {
    param([string]$Path, [int]$ProcessId, [int]$Port, [string]$Engine)
    [void][System.IO.Directory]::CreateDirectory((Split-Path -Parent $Path))
    [System.IO.File]::WriteAllText($Path, ('{0};{1};{2}' -f $ProcessId, $Port, $Engine), (New-Object System.Text.ASCIIEncoding))
}

# ------------------------------------------------------------------ quoting

function ConvertTo-QuotedArg {
    param([AllowEmptyString()][string]$Value)
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('"')
    $backslashes = 0
    foreach ($ch in $Value.ToCharArray()) {
        if ($ch -eq [char]92) {
            $backslashes++
            continue
        }
        if ($ch -eq [char]34) {
            [void]$sb.Append('\' * (2 * $backslashes + 1))
            [void]$sb.Append('"')
        } else {
            if ($backslashes -gt 0) { [void]$sb.Append('\' * $backslashes) }
            [void]$sb.Append($ch)
        }
        $backslashes = 0
    }
    if ($backslashes -gt 0) { [void]$sb.Append('\' * (2 * $backslashes)) }
    [void]$sb.Append('"')
    return $sb.ToString()
}

function ConvertTo-ProcessArgString {
    param([AllowEmptyCollection()][string[]]$ArgumentList = @())
    $quoted = foreach ($a in $ArgumentList) { ConvertTo-QuotedArg -Value $a }
    return (@($quoted) -join ' ')
}

# ------------------------------------------------------------------ WSL

function Find-WslExe {
    param([string]$WslExe = '')
    if ($WslExe) {
        if (Test-Path -LiteralPath $WslExe -PathType Leaf) { return (Resolve-Path -LiteralPath $WslExe).ProviderPath }
        return $null
    }
    $root = $env:SystemRoot
    if (-not $root) { $root = $env:windir }
    if (-not $root) { return $null }
    # A 32-bit PowerShell sees SysWOW64 as System32; Sysnative reaches the real System32.
    foreach ($sub in @('System32', 'Sysnative')) {
        $candidate = Join-Path (Join-Path $root $sub) 'wsl.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

function Set-ConsoleUtf8 {
    try {
        $previous = [Console]::OutputEncoding
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
        return $previous
    } catch {
        return $null
    }
}

function Restore-ConsoleEncoding {
    param($Previous)
    if ($null -eq $Previous) { return }
    try { [Console]::OutputEncoding = $Previous } catch { }
}

function ConvertFrom-WslListText {
    param([AllowEmptyString()][string]$Text)
    $found = New-Object System.Collections.ArrayList
    if (-not $Text) { return $found.ToArray() }
    # Without WSL_UTF8 support wsl.exe writes UTF-16LE, which decodes as text with NULs between characters.
    $clean = $Text.Replace([string][char]0, '').Replace([string][char]0xFEFF, '')
    $lines = @($clean -split "\r?\n" | Where-Object { $_.Trim() -ne '' })
    # The first line is the (possibly localized) NAME/STATE/VERSION header.
    for ($i = 1; $i -lt $lines.Count; $i++) {
        $line = $lines[$i].Trim()
        $isDefault = $line.StartsWith('*')
        if ($isDefault) { $line = $line.Substring(1).Trim() }
        $tokens = @($line -split '\s+' | Where-Object { $_ -ne '' })
        if ($tokens.Count -lt 3) { continue }
        $version = $tokens[$tokens.Count - 1]
        if ($version -notmatch '^\d+$') { continue }
        $name = ($tokens[0..($tokens.Count - 3)]) -join ' '
        [void]$found.Add([pscustomobject]@{
            Name    = $name
            State   = $tokens[$tokens.Count - 2]
            Version = [int]$version
            Default = $isDefault
        })
    }
    return $found.ToArray()
}

function Get-WslDistros {
    param([Parameter(Mandatory = $true)][string]$WslExe)
    $env:WSL_UTF8 = '1'
    $previous = Set-ConsoleUtf8
    try {
        $out = & $WslExe '-l' '-v' 2>$null
        $code = $LASTEXITCODE
    } catch {
        $out = @()
        $code = 1
    } finally {
        Restore-ConsoleEncoding $previous
    }
    Write-GeoLog 'INFO' ('wsl -l -v exit ' + $code)
    if ($code -ne 0) { return @() }
    $text = (@($out) | ForEach-Object { [string]$_ }) -join "`n"
    return (ConvertFrom-WslListText -Text $text)
}

function Test-WslStatus {
    param([Parameter(Mandatory = $true)][string]$WslExe)
    $env:WSL_UTF8 = '1'
    try {
        & $WslExe '--status' *> $null
        $code = $LASTEXITCODE
    } catch {
        $code = 1
    }
    Write-GeoLog 'INFO' ('wsl --status exit ' + $code)
    return ($code -eq 0)
}

function New-WslArgv {
    param(
        [Parameter(Mandatory = $true)][string]$Distro,
        [string]$Cd = '',
        [string]$User = '',
        [Parameter(Mandatory = $true)][string]$Exec,
        [AllowEmptyCollection()][string[]]$Arguments = @()
    )
    $argv = New-Object System.Collections.Generic.List[string]
    $argv.Add('-d')
    $argv.Add($Distro)
    if ($User) { $argv.Add('-u'); $argv.Add($User) }
    if ($Cd) { $argv.Add('--cd'); $argv.Add($Cd) }
    $argv.Add('--exec')
    $argv.Add($Exec)
    foreach ($a in $Arguments) { $argv.Add([string]$a) }
    foreach ($a in $argv) {
        # Windows PowerShell 5.1 drops empty native arguments and does not escape embedded double quotes.
        if ($a.Length -eq 0 -or $a.Contains('"')) {
            throw ('WSL argument rejected (empty or contains a double quote): [' + $a + ']')
        }
    }
    return ,$argv.ToArray()
}

function Invoke-WslExec {
    param(
        [Parameter(Mandatory = $true)][string]$WslExe,
        [Parameter(Mandatory = $true)][string]$Distro,
        [string]$Cd = '',
        [string]$User = '',
        [Parameter(Mandatory = $true)][string]$Exec,
        [AllowEmptyCollection()][string[]]$Arguments = @()
    )
    $argv = New-WslArgv -Distro $Distro -Cd $Cd -User $User -Exec $Exec -Arguments $Arguments
    $env:WSL_UTF8 = '1'
    Write-GeoLog 'INFO' ('wsl.exe ' + (ConvertTo-ProcessArgString -ArgumentList $argv))
    $previous = Set-ConsoleUtf8
    try {
        $out = & $WslExe @argv
        $code = $LASTEXITCODE
    } catch {
        $out = @()
        $code = 1
        Write-GeoLog 'ERROR' ('wsl.exe could not be run: ' + $_.Exception.Message)
    } finally {
        Restore-ConsoleEncoding $previous
    }
    if ($null -eq $code) { $code = 1 }
    $text = (@($out) | ForEach-Object { [string]$_ }) -join "`n"
    Write-GeoLog 'INFO' ('wsl.exe exit ' + $code)
    return [pscustomobject]@{ ExitCode = [int]$code; Stdout = $text }
}

function Start-WslHidden {
    param(
        [Parameter(Mandatory = $true)][string]$WslExe,
        [Parameter(Mandatory = $true)][string]$Distro,
        [string]$Cd = '',
        [Parameter(Mandatory = $true)][string]$Exec,
        [AllowEmptyCollection()][string[]]$Arguments = @()
    )
    $argv = New-WslArgv -Distro $Distro -Cd $Cd -Exec $Exec -Arguments $Arguments
    $argString = ConvertTo-ProcessArgString -ArgumentList $argv
    $env:WSL_UTF8 = '1'
    Write-GeoLog 'INFO' ('start hidden: wsl.exe ' + $argString)
    $proc = Start-Process -FilePath $WslExe -ArgumentList $argString -WindowStyle Hidden -PassThru
    # Touching Handle keeps ExitCode readable after the process has exited.
    $null = $proc.Handle
    return $proc
}

function ConvertFrom-PilotJson {
    param([AllowEmptyString()][string]$Text)
    if (-not $Text) { return $null }
    $lines = @($Text -split "\r?\n" | Where-Object { $_.Trim().StartsWith('{') })
    if ($lines.Count -eq 0) { return $null }
    try {
        return ($lines[$lines.Count - 1] | ConvertFrom-Json -ErrorAction Stop)
    } catch {
        return $null
    }
}

# ------------------------------------------------------------------ ports and health

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

function Test-UiHealth {
    param([int]$Port)
    try {
        $r = Invoke-WebRequest -Uri ('http://127.0.0.1:{0}/_stcore/health' -f $Port) -TimeoutSec 5 -UseBasicParsing
        return ("$($r.Content)" -match 'ok')
    } catch {
        return $false
    }
}

function Wait-UiHealth {
    param([int]$Port, [int]$Seconds = 90, $Process = $null)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-UiHealth -Port $Port) { return $true }
        if ($null -ne $Process -and $Process.HasExited) { return $false }
        Start-Sleep -Seconds 2
    }
    return $false
}

# ------------------------------------------------------------------ messages

function Get-PilotMessage {
    param([int]$Code, [string]$Action = '')
    switch ($Code) {
        0 {
            if ($Action -eq 'pilot') { return 'Sinirli gelistirme pilotu baslatildi (CPU, yalniz train/val-select/val-calib). Bu bir benchmark degildir.' }
            return 'Islem basarili.'
        }
        1 { return 'Beklenmeyen bir hata olustu. Ayrintilar: windows\logs\geo_workbench.log' }
        2 { return 'WSL2 arka ucu henuz kurulmamis. Gercek RF pilotu icin once masaustundeki "GEO WSL Kurulumu" kisayolunu calistirin. Pano simdilik yalniz inceleme modunda acilir.' }
        3 {
            if ($Action -in @('stop-pilot', 'close', 'status')) { return 'Calisan bir GEO pilotu yok; durdurulacak bir sey bulunamadi.' }
            return 'WSL (wsl.exe), kayitli Ubuntu dagitimi veya WSL icindeki GEO kopyasi bulunamadi. "GEO WSL Kurulumu" kisayolunu yeniden calistirin.'
        }
        4 { return 'Pano 90 saniye icinde saglik kontrolune yanit vermedi. Gunlukler: windows\logs\geo_workbench.log ve WSL icinde ~/.local/share/geo-dashboard/workbench/ui.log' }
        5 { return 'Islem onaylanmadi; hicbir sey degistirilmedi.' }
        6 { return 'Pilot denetcisi baslatildi ancak is kimligi 60 saniye icinde gorulmedi. Durumu panodan veya "GEO Workbench" ile kontrol edin; ikinci kez baslatmayin.' }
        7 { return 'WSL/Ubuntu kurulumu baslatildi. Kurulum bitince (Windows isterse bilgisayari yeniden baslatip) "GEO WSL Kurulumu" kisayolunu tekrar calistirin.' }
        8 { return 'WSL dagitimi uygun degil: WSL2 ve python3 >= 3.10 gerekir.' }
        9 { return 'Paket dosyalari eksik (VERSION.json, SOURCE_MANIFEST.json veya windows\wsl\geo_wsl_setup.py). WSL kurulumu yalniz CI tarafindan uretilen ZIP paketinden yapilabilir.' }
        10 { return 'Bir GEO pilotu zaten calisiyor; ikinci pilot baslatilmadi. Mevcut is kimligi asagidadir.' }
        11 { return 'Pano zaten calisiyor; mevcut kopya kullaniliyor.' }
        12 { return 'Pano portu dolu (8531-8540). Bu portlari kullanan uygulamalari kapatip yeniden deneyin.' }
        13 { return 'WSL icinde mevcut bir GEO kurulumu var; degistirmek ayri onay gerektirir.' }
        14 { return 'Hedef klasor bir Windows surucusu (/mnt/...) altinda olamaz; kurulum WSL ext4 ev dizinine yapilir.' }
        15 { return 'WSL icinde python3-venv paketi eksik (sudo apt-get install -y python3-venv).' }
        16 { return 'pip paket kurulumu basarisiz oldu. Internet/proxy baglantisini kontrol edip "GEO WSL Kurulumu" kisayolunu yeniden calistirin.' }
        20 { return 'Kaynak kimligi dogrulanamadi: WSL icindeki kopya bu paketin commit/manifest degerleriyle eslesmiyor veya degistirilmis. "GEO WSL Kurulumu" kisayolunu yeniden calistirin.' }
        21 { return 'Bu ortam gercek RF pilotunu calistiramaz; WSL2 Ubuntu (veya Linux) gerekir.' }
        22 { return 'Gerekli Python paketleri (torch, numpy, scipy) WSL ortaminda eksik. "GEO WSL Kurulumu" kisayolunu yeniden calistirin.' }
        23 { return 'Yetersiz disk alani: WSL cikti klasorunde en az 5 GiB bos alan gerekir.' }
        24 { return 'Grup sayisi reddedildi; yalniz 1 veya 2 grup kabul edilir.' }
        30 { return 'Pilot BASARISIZ bitti. Gunluk ve kismi ciktilar korundu.' }
        31 { return 'Pilot iptal edildi. Kismi ciktilar ve gunluk korundu; sonuc basarili sayilmaz.' }
        32 { return 'Pilot zaman asimina ugradi. Ciktilar korundu; sonuc basarili sayilmaz.' }
        33 { return 'Pilot sureci, sonucu kaydedilmeden bitti (finished_unrecorded); basari varsayilmaz.' }
        34 { return 'Pilot kaydi (job.json) okunamiyor (record_unreadable); basari varsayilmaz, kayit degistirilmedi.' }
        40 { return 'Komut, guvenlik katmani tarafindan reddedildi.' }
        41 { return 'Sahiplik dogrulanamadi: kayitli PID artik baska bir surece ait. Hicbir surec sonlandirilmadi.' }
    }
    return ('Bilinmeyen cikis kodu: ' + $Code + '. Ayrintilar: windows\logs\geo_workbench.log')
}
